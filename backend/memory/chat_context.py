"""Per-chat context window: normalize history, trim by message count and character budget."""

from __future__ import annotations

import os
from typing import Any

# Tunable via environment (strong defaults for long threads)
CHAT_MAX_HISTORY_MESSAGES: int = max(8, int(os.getenv("CHAT_MAX_HISTORY_MESSAGES", "48")))
CHAT_MAX_HISTORY_CHARS: int = max(4000, int(os.getenv("CHAT_MAX_HISTORY_CHARS", "36000")))


def normalize_history_messages(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Keep only user/assistant pairs with non-empty string content."""
    out: list[dict[str, str]] = []
    for m in history:
        role = m.get("role")
        content = m.get("content")
        if role not in ("user", "assistant"):
            continue
        text = str(content or "").strip()
        if not text:
            continue
        out.append({"role": role, "content": text})
    return out


def apply_context_window(
    messages: list[dict[str, str]],
    *,
    max_messages: int | None = None,
    max_chars: int | None = None,
) -> list[dict[str, str]]:
    """
    Keep the most recent messages, then drop from the front until under max_chars
    (always keep at least the last two messages if possible).
    """
    cap_m = max_messages if max_messages is not None else CHAT_MAX_HISTORY_MESSAGES
    cap_c = max_chars if max_chars is not None else CHAT_MAX_HISTORY_CHARS
    if not messages:
        return []
    trimmed = messages[-cap_m:] if len(messages) > cap_m else list(messages)
    while len(trimmed) > 2:
        total = sum(len(m["content"]) for m in trimmed)
        if total <= cap_c:
            break
        trimmed = trimmed[1:]
    return trimmed


def strip_trailing_user_matching_message(
    messages: list[dict[str, str]],
    current_user_message: str,
) -> list[dict[str, str]]:
    """Avoid duplicating the current user turn (already sent as augmented_prompt / final user message)."""
    cur = (current_user_message or "").strip()
    if not cur or not messages:
        return messages
    out = list(messages)
    while out and out[-1]["role"] == "user" and out[-1]["content"].strip() == cur:
        out.pop()
    return out


def build_system_context_extension(rolling_summary: str) -> str:
    """Append to system prompt when older turns were compressed into a rolling summary."""
    s = (rolling_summary or "").strip()
    if not s:
        return ""
    return (
        "\n\n## Earlier in this chat (compressed summary)\n"
        f"{s}\n"
        "Use this only for continuity; the latest messages below are authoritative."
    )
