"""Persistent chat storage — saves conversations as JSON files to disk."""

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CHATS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "chats"


def _ensure_dir() -> None:
    CHATS_DIR.mkdir(parents=True, exist_ok=True)


def _chat_path(chat_id: str) -> Path:
    return CHATS_DIR / f"{chat_id}.json"


def save_chat(chat_id: str, title: str, messages: list[dict[str, Any]]) -> dict:
    """Save or update a chat. Returns the saved metadata."""
    _ensure_dir()
    path = _chat_path(chat_id)

    existing = None
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))

    data = {
        "id": chat_id,
        "title": title,
        "messages": messages,
        "created_at": existing["created_at"] if existing else time.time(),
        "updated_at": time.time(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def load_chat(chat_id: str) -> dict | None:
    """Load a single chat by ID. Returns None if not found."""
    path = _chat_path(chat_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def delete_chat(chat_id: str) -> bool:
    """Delete a chat. Returns True if it existed."""
    path = _chat_path(chat_id)
    if path.exists():
        path.unlink()
        return True
    return False


def list_chats() -> list[dict]:
    """Return all chats sorted by most recent first (metadata only, no messages)."""
    _ensure_dir()
    chats = []
    for path in CHATS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            preview = ""
            for msg in data.get("messages", []):
                if msg.get("role") == "user":
                    preview = msg["content"][:80]
                    break
            chats.append({
                "id": data["id"],
                "title": data.get("title", "Untitled"),
                "preview": preview,
                "message_count": len(data.get("messages", [])),
                "created_at": data.get("created_at", 0),
                "updated_at": data.get("updated_at", 0),
            })
        except Exception as e:
            logger.warning("Failed to read chat %s: %s", path.name, e)
    chats.sort(key=lambda c: c["updated_at"], reverse=True)
    return chats


def generate_title(messages: list[dict[str, Any]]) -> str:
    """Derive a short title from the first user message."""
    for msg in messages:
        if msg.get("role") == "user" and msg.get("content"):
            text = msg["content"].strip()
            if len(text) <= 40:
                return text
            return text[:37] + "..."
    return "New chat"
