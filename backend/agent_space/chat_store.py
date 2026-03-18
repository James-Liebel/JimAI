"""Chat thread store for Agent Space UI."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .paths import CHATS_DIR, ensure_layout


class AgentSpaceChatStore:
    """Persist chat threads as JSON files."""

    def __init__(self) -> None:
        ensure_layout()

    def _path(self, thread_id: str) -> Path:
        return CHATS_DIR / f"{thread_id}.json"

    def list_threads(self, limit: int = 100) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in CHATS_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            rows.append(
                {
                    "id": data.get("id"),
                    "title": data.get("title", "Untitled"),
                    "updated_at": data.get("updated_at", 0),
                    "message_count": len(data.get("messages", [])),
                }
            )
        rows.sort(key=lambda row: row["updated_at"], reverse=True)
        return rows[: max(1, limit)]

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        path = self._path(thread_id)
        if not path.exists():
            return {"id": thread_id, "title": "New Thread", "messages": [], "updated_at": time.time()}
        return json.loads(path.read_text(encoding="utf-8"))

    def append_message(self, thread_id: str, role: str, content: str) -> dict[str, Any]:
        thread = self.get_thread(thread_id)
        thread.setdefault("messages", []).append(
            {"role": role, "content": content, "timestamp": time.time()}
        )
        if not thread.get("title") or thread.get("title") == "New Thread":
            if role == "user" and content:
                thread["title"] = content[:50]
        thread["id"] = thread_id
        thread["updated_at"] = time.time()
        self._path(thread_id).write_text(json.dumps(thread, ensure_ascii=False, indent=2), encoding="utf-8")
        return thread

