"""Autonomous thought generator — periodic background reflection.

Most user-facing AI is purely reactive: it answers when spoken to and forgets
between turns. This module gives the system its own slow loop. When the
backend has been idle for a few minutes, it:

  1. Reads the user's recent chat-turn fragments from the vector store,
  2. Asks the chat model to surface CONNECTIONS, HYPOTHESES, and OPEN QUESTIONS
     across those fragments (not summarize them — *think* about them),
  3. Stores the result as a structured "thoughts" memory slot that the chat
     system prompt surfaces back in the next user turn.

The thoughts then influence subsequent answers (the model sees its own
prior reflections) and form the basis for proactive suggestions.

Storage is per-user (db.user_memory slot ``autonomous_thoughts``) so it
doesn't leak across user profiles. The slot is rotated — only the most
recent N thought-batches are kept.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

from config.models import TURBO_CONFIGS
from memory import db, vectordb
from models import ollama_client

logger = logging.getLogger(__name__)

_SLOT = "autonomous_thoughts"
_MAX_BATCHES = 8
_IDLE_WINDOW_SECONDS = 180.0     # consider the system idle if no activity in this window
_TICK_INTERVAL_SECONDS = 600.0   # how often the loop wakes up
_MIN_TURNS_FOR_REFLECTION = 4    # don't reflect with too little material

# Background reflection runs with no user present, so it must stay cheap: always
# use the smallest installed chat model (turbo tier — a 3B), never the user's
# active speed tier (up to 32B on Deep). Override via JIMAI_BACKGROUND_MODEL.
_BACKGROUND_MODEL = os.getenv("JIMAI_BACKGROUND_MODEL", TURBO_CONFIGS["chat"].model)

_REFLECTION_SYSTEM = (
    "You are the user's quiet thinking partner. The user is not in the room. "
    "Read the recent conversation fragments and surface the things that aren't "
    "obvious from any one fragment alone. Your output drives proactive "
    "suggestions the next time the user shows up — focus on signal, not summary."
)

_REFLECTION_PROMPT_TEMPLATE = """Recent conversation fragments (each is one turn):

{fragments}

Produce a JSON object in this exact shape — no markdown, no preamble:
{{
  "connections": [
    "<one sentence connecting two or more fragments — only if non-obvious>"
  ],
  "hypotheses": [
    "<a plausible claim about the user's goals, project, or constraints that the fragments support but never state outright>"
  ],
  "open_questions": [
    "<a concrete question the user has not asked yet but should — phrased so the next answer would unblock progress>"
  ],
  "follow_ups": [
    "<a specific action the assistant should proactively offer the user next time>"
  ]
}}

Rules:
- Each list 1–4 items, omit a list entirely if you have nothing real to add.
- Never invent biographical facts. Stay grounded in what the fragments imply.
- Prefer specific to generic. "User is building X in Y because Z" beats "user works on AI".
"""


# Track when the system was last touched so the loop can detect idle windows.
_LAST_ACTIVITY_TS: float = time.time()


def note_activity() -> None:
    """Hook the rest of the system can call to mark the user as active.
    Currently called from the chat path; can be invoked from any other entry
    point that represents user-driven work."""
    global _LAST_ACTIVITY_TS
    _LAST_ACTIVITY_TS = time.time()


def get_thoughts(user_id: str = db.DEFAULT_USER_ID) -> dict[str, Any]:
    """Read the latest persisted thought batch for prompt injection.
    Returns {} if there isn't one yet."""
    rec = db.read_user_slot(user_id, _SLOT)
    if rec is None or not isinstance(rec.get("data"), dict):
        return {}
    data = rec["data"]
    batches = data.get("batches") or []
    if not batches:
        return {}
    return dict(batches[-1])


def build_thoughts_prompt_block(user_id: str = db.DEFAULT_USER_ID) -> str:
    """Render the most recent thought batch as a system-prompt block. Returns
    empty string if no thoughts exist or the batch is empty."""
    latest = get_thoughts(user_id)
    if not latest:
        return ""
    sections: list[str] = []
    for key, header in (
        ("connections", "Connections noticed"),
        ("hypotheses", "Working hypotheses about you"),
        ("open_questions", "Questions you have not asked but probably should"),
        ("follow_ups", "Things to proactively offer"),
    ):
        items = [str(x).strip() for x in (latest.get(key) or []) if str(x).strip()]
        if not items:
            continue
        sections.append(f"### {header}\n" + "\n".join(f"- {x}" for x in items[:4]))
    if not sections:
        return ""
    return (
        "## Your own prior reflections (generated quietly between turns)\n"
        "Use these as soft priors — they may be wrong; cross-check before relying.\n\n"
        + "\n\n".join(sections)
    )


def _persist_batch(user_id: str, batch: dict[str, Any]) -> None:
    rec = db.read_user_slot(user_id, _SLOT) or {}
    existing = rec.get("data") if isinstance(rec, dict) else None
    if not isinstance(existing, dict):
        existing = {"batches": []}
    batches = list(existing.get("batches") or [])
    batches.append({**batch, "created_at": time.time()})
    if len(batches) > _MAX_BATCHES:
        batches = batches[-_MAX_BATCHES:]
    db.write_user_slot(user_id, _SLOT, {"batches": batches, "version": 1})


def _parse_reflection(raw: str) -> dict[str, Any]:
    """Tolerant JSON parser — strips fences, trailing commas, smart quotes."""
    if not raw:
        return {}
    text = raw.strip()
    # Strip ```json fences if present.
    if "```" in text:
        import re
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()
    text = (
        text.replace("“", '"').replace("”", '"')
        .replace("‘", "'").replace("’", "'")
    )
    # Drop trailing commas.
    import re
    text = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {}


async def _collect_recent_fragments(user_id: str, n: int = 12) -> list[str]:
    """Pull recent chat-turn documents straight from ChromaDB without an
    embedding query — we want recency not similarity. Falls back to empty if
    the collection doesn't expose what we need."""
    try:
        collection = vectordb._get_collection()
        if collection is None:
            return []
        try:
            all_docs = collection.get(
                where={"$and": [
                    {"user_id": {"$eq": user_id}},
                    {"kind": {"$eq": "chat_turn"}},
                ]},
                include=["documents", "metadatas"],
            )
        except Exception:
            # Older Chroma collections may not have user_id; degrade to kind-only.
            try:
                all_docs = collection.get(
                    where={"kind": {"$eq": "chat_turn"}},
                    include=["documents", "metadatas"],
                )
            except Exception:
                return []
        docs = all_docs.get("documents") or []
        metas = all_docs.get("metadatas") or []
        paired = list(zip(docs, metas))
        # Sort by timestamp_ms descending, take the latest n.
        paired.sort(key=lambda dm: int(dm[1].get("timestamp_ms") or 0), reverse=True)
        return [d for d, _ in paired[:n] if isinstance(d, str) and d.strip()]
    except Exception as exc:
        logger.debug("thought_generator: could not collect fragments: %s", exc)
        return []


def _ai_power_enabled() -> bool:
    """Honor the global power switch: when the user turns the AI off, background
    reflection must not load a model on its own. Defaults to enabled if the power
    manager can't be reached, so an import hiccup doesn't silently kill the feature."""
    try:
        from agent_space.runtime import power_manager
        return power_manager.is_enabled()
    except Exception:
        return True


async def reflect_once(user_id: str = db.DEFAULT_USER_ID) -> dict[str, Any]:
    """Run one reflection pass and persist the result. Returns the new batch
    (or {} on failure). Public so a route can trigger reflection on demand."""
    if not _ai_power_enabled():
        return {}
    fragments = await _collect_recent_fragments(user_id)
    if len(fragments) < _MIN_TURNS_FOR_REFLECTION:
        return {}
    # Truncate each fragment so we don't blow the context window.
    capped = [f[:1200] for f in fragments[:12]]
    prompt = _REFLECTION_PROMPT_TEMPLATE.format(
        fragments="\n\n---\n\n".join(capped),
    )
    try:
        raw = await ollama_client.generate_full(
            model=_BACKGROUND_MODEL,
            prompt=prompt,
            system=_REFLECTION_SYSTEM,
            temperature=0.4,
            num_ctx=8192,
            num_predict=768,
            repeat_penalty=1.05,
        )
    except Exception as exc:
        logger.debug("thought_generator: model call failed: %s", exc)
        return {}
    parsed = _parse_reflection(raw)
    if not parsed:
        return {}
    # Validate shape — discard non-list entries silently.
    clean: dict[str, Any] = {}
    for key in ("connections", "hypotheses", "open_questions", "follow_ups"):
        val = parsed.get(key)
        if isinstance(val, list):
            clean[key] = [str(x).strip() for x in val if str(x).strip()][:4]
    if not any(clean.values()):
        return {}
    _persist_batch(user_id, clean)
    logger.info("thought_generator: persisted reflection (%d categories) for %s", len(clean), user_id)
    return clean


async def _loop() -> None:
    while True:
        try:
            await asyncio.sleep(_TICK_INTERVAL_SECONDS)
            idle_for = time.time() - _LAST_ACTIVITY_TS
            if idle_for < _IDLE_WINDOW_SECONDS:
                # User is active — don't burn cycles on background reflection
                # while the model is busy serving real requests.
                continue
            await reflect_once(db.DEFAULT_USER_ID)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("thought_generator loop iteration failed", exc_info=True)


def start_background_loop() -> None:
    """Spawn the periodic reflection task. Safe to call multiple times — the
    first call wins; subsequent calls are no-ops once a loop is registered."""
    from agent_space import background_tasks

    global _LOOP_TASK
    try:
        _LOOP_TASK
    except NameError:
        _LOOP_TASK = None  # type: ignore[name-defined]
    if _LOOP_TASK and not _LOOP_TASK.done():
        return
    _LOOP_TASK = background_tasks.spawn(_loop(), name="autonomous_thoughts")


_LOOP_TASK = None  # type: ignore[assignment]
