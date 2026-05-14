"""Background tasks: per-chat rolling summary + cross-chat notes."""

from __future__ import annotations

import logging
from typing import Any

from memory import session as session_store
from memory import cross_chat_memory

logger = logging.getLogger(__name__)

_ROLLING_THRESHOLD = 18
_ROLLING_KEEP_RECENT = 10
_SUMMARY_MAX_CHARS = 3500


async def _summarize_messages_block(messages: list[dict[str, str]], model: str) -> str:
    from models import ollama_client

    lines = []
    for m in messages:
        role = m["role"]
        body = m["content"][:2000]
        lines.append(f"{role.upper()}: {body}")
    blob = "\n".join(lines)
    prompt = (
        "Summarize the following older chat turns for the assistant's memory. "
        "Output at most 10 short bullet points. Focus on facts, decisions, open tasks, "
        "and user preferences. No preamble—bullets only, each starting with '-'.\n\n"
        f"{blob[:12000]}"
    )
    try:
        text = await ollama_client.generate_full(
            model=model,
            prompt=prompt,
            system="Be concise. Bullet list only.",
            temperature=0.2,
        )
        t = text.strip()
        if len(t) > _SUMMARY_MAX_CHARS:
            t = t[:_SUMMARY_MAX_CHARS] + "…"
        return t
    except Exception:
        logger.warning("rolling summary generation failed", exc_info=True)
        return ""


async def after_turn(
    session_id: str,
    user_message: str,
    assistant_message: str,
    history_snapshot: list[dict[str, Any]],
    user_id: str = "default",
) -> None:
    """
    history_snapshot: normalized full history including this turn (role/content), from the client path.
    """
    from models.router import get_model_config

    cfg = get_model_config("chat")
    model = cfg.model

    flat = [
        {"role": m["role"], "content": m["content"]}
        for m in history_snapshot
        if m.get("role") in ("user", "assistant") and str(m.get("content") or "").strip()
    ]

    # Per-chat rolling summary (in-memory session)
    if len(flat) >= _ROLLING_THRESHOLD:
        older = flat[: -_ROLLING_KEEP_RECENT]
        if older:
            summary = await _summarize_messages_block(older, model)
            if summary:
                session = session_store.get_session(session_id)
                prev = str(session.get("rolling_summary") or "").strip()
                if prev:
                    session["rolling_summary"] = f"{prev}\n\n{summary}"[:_SUMMARY_MAX_CHARS]
                else:
                    session["rolling_summary"] = summary[:_SUMMARY_MAX_CHARS]

    # Cross-chat: short note for consolidation
    note = (
        f"User asked: {user_message[:400]}\n"
        f"Assistant replied (excerpt): {assistant_message[:500]}"
    )
    cross_chat_memory.append_pending(note, user_id=user_id)

    # Index this turn into the vector store so future questions can RAG over
    # past conversations. Source ``history:<user_id>`` is a stable per-user
    # bucket; chat.py augments its session_sources with this string at retrieve
    # time. Failure is best-effort — embedding can fail if Ollama is down or
    # nomic-embed-text isn't pulled, in which case we keep current-chat-only
    # behavior.
    try:
        from memory import vectordb
        import hashlib
        import time

        turn_text = (
            f"USER: {user_message}\n"
            f"ASSISTANT: {assistant_message}"
        )
        history_source = f"history:{user_id}"
        ts = int(time.time() * 1000)
        turn_source = f"{history_source}:{session_id}:{ts}"
        # Hash the assistant response so the feedback API can target this
        # turn's chunks without needing a frontend-assigned message_id.
        response_hash = hashlib.sha1(assistant_message.encode("utf-8", "replace")).hexdigest()[:24]
        await vectordb.ingest_document(
            text=turn_text,
            source=turn_source,
            metadata={
                "user_id": user_id,
                "session_id": session_id,
                "kind": "chat_turn",
                "timestamp_ms": ts,
                "response_hash": response_hash,
                # feedback_score starts at 0; adjust_metadata bumps it per feedback event.
                "feedback_score": 0.0,
            },
        )
    except Exception:
        logger.debug("chat-turn vectordb ingest skipped", exc_info=True)


def schedule_after_turn(
    session_id: str,
    user_message: str,
    assistant_message: str,
    history_snapshot: list[dict[str, Any]],
    user_id: str = "default",
) -> None:
    try:
        import asyncio

        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _run() -> None:
        try:
            await after_turn(session_id, user_message, assistant_message, history_snapshot, user_id=user_id)
        except Exception:
            logger.warning("chat_memory_jobs.after_turn failed", exc_info=True)

    from agent_space.background_tasks import spawn
    spawn(_run(), name=f"chat_memory:{session_id}")


def normalize_snapshot(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in history:
        if m.get("role") not in ("user", "assistant"):
            continue
        c = str(m.get("content") or "").strip()
        if c:
            out.append({"role": m["role"], "content": c})
    return out
