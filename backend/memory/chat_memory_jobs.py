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
    cross_chat_memory.append_pending(note)


def schedule_after_turn(
    session_id: str,
    user_message: str,
    assistant_message: str,
    history_snapshot: list[dict[str, Any]],
) -> None:
    try:
        import asyncio

        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _run() -> None:
        try:
            await after_turn(session_id, user_message, assistant_message, history_snapshot)
        except Exception:
            logger.warning("chat_memory_jobs.after_turn failed", exc_info=True)

    loop.create_task(_run())


def normalize_snapshot(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in history:
        if m.get("role") not in ("user", "assistant"):
            continue
        c = str(m.get("content") or "").strip()
        if c:
            out.append({"role": m["role"], "content": c})
    return out
