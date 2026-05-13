"""Persistent chat storage — SQLite-backed, scales to many rows.

Same public surface (save_chat / load_chat / delete_chat / list_chats /
generate_title) so existing callers keep working. On first call the legacy
JSON files at data/chats/*.json are imported once, then ignored.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import db

logger = logging.getLogger(__name__)

LEGACY_CHATS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "chats"
_MIGRATED = False


def _ensure_migrated() -> None:
    global _MIGRATED
    if _MIGRATED:
        return
    try:
        n = db.migrate_json_chats_if_needed(LEGACY_CHATS_DIR)
        if n:
            logger.info("chat_store: imported %d legacy JSON chats into SQLite", n)
    except Exception:
        logger.exception("chat_store: legacy JSON migration failed (continuing)")
    _MIGRATED = True


def save_chat(
    chat_id: str,
    title: str,
    messages: list[dict[str, Any]],
    user_id: str = db.DEFAULT_USER_ID,
) -> dict:
    _ensure_migrated()
    return db.upsert_chat(chat_id, title, messages, user_id=user_id)


def load_chat(chat_id: str) -> dict | None:
    _ensure_migrated()
    return db.load_chat_row(chat_id)


def delete_chat(chat_id: str) -> bool:
    _ensure_migrated()
    return db.delete_chat_row(chat_id)


def list_chats(user_id: str | None = None) -> list[dict]:
    """Return chats sorted by most recent first (metadata only, no messages)."""
    _ensure_migrated()
    return db.list_chats_rows(user_id=user_id)


def generate_title(messages: list[dict[str, Any]]) -> str:
    """Derive a short title from the first user message."""
    for msg in messages:
        if msg.get("role") == "user" and msg.get("content"):
            text = str(msg["content"]).strip()
            if len(text) <= 40:
                return text
            return text[:37] + "..."
    return "New chat"
