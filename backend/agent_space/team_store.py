"""Persistent agent team definitions and team message history."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from .paths import TEAMS_DIR, ensure_layout


class TeamStore:
    """Stores reusable team specs and message archives."""

    def __init__(self) -> None:
        ensure_layout()
        self._cache: dict[str, dict[str, Any]] = {}

    def _path(self, team_id: str) -> Path:
        return TEAMS_DIR / f"{team_id}.json"

    def list_teams(self, limit: int = 200) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in TEAMS_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            team_id = str(data.get("id", "")).strip()
            if team_id:
                self._cache[team_id] = dict(data)
            rows.append(
                {
                    "id": data.get("id"),
                    "name": data.get("name", "Unnamed Team"),
                    "description": data.get("description", ""),
                    "agent_count": len(data.get("agents", [])),
                    "created_at": data.get("created_at", 0),
                    "updated_at": data.get("updated_at", 0),
                }
            )
        for cached in self._cache.values():
            if not any(str(row.get("id")) == str(cached.get("id")) for row in rows):
                rows.append(
                    {
                        "id": cached.get("id"),
                        "name": cached.get("name", "Unnamed Team"),
                        "description": cached.get("description", ""),
                        "agent_count": len(cached.get("agents", [])),
                        "created_at": cached.get("created_at", 0),
                        "updated_at": cached.get("updated_at", 0),
                    }
                )
        rows.sort(key=lambda row: row.get("updated_at", 0), reverse=True)
        return rows[: max(1, limit)]

    def get_team(self, team_id: str) -> dict[str, Any] | None:
        cached = self._cache.get(team_id)
        if cached is not None:
            return dict(cached)
        path = self._path(team_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        self._cache[team_id] = dict(data)
        return data

    def save_team(
        self,
        *,
        team_id: str | None,
        name: str,
        agents: list[dict[str, Any]],
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing = self.get_team(team_id) if team_id else None
        team_id = team_id or str(uuid.uuid4())
        data = {
            "id": team_id,
            "name": name or "Unnamed Team",
            "description": description or "",
            "agents": agents,
            "metadata": metadata or {},
            "messages": existing.get("messages", []) if existing else [],
            "created_at": existing.get("created_at") if existing else time.time(),
            "updated_at": time.time(),
        }
        self._write(team_id, data)
        return data

    def delete_team(self, team_id: str) -> bool:
        self._cache.pop(team_id, None)
        path = self._path(team_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def append_message(
        self,
        team_id: str,
        *,
        run_id: str,
        from_agent: str,
        content: str,
        to_agent: str = "",
        channel: str = "general",
    ) -> dict[str, Any]:
        team = self.get_team(team_id)
        if team is None:
            raise FileNotFoundError(f"Team '{team_id}' not found.")
        msg = {
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "run_id": run_id,
            "from": from_agent,
            "to": to_agent,
            "channel": channel or "general",
            "content": content,
        }
        messages = list(team.get("messages", []))
        messages.append(msg)
        team["messages"] = messages[-2000:]
        team["updated_at"] = time.time()
        self._write(team_id, team)
        return msg

    def list_messages(
        self,
        team_id: str,
        *,
        limit: int = 200,
        run_id: str | None = None,
        channel: str | None = None,
    ) -> list[dict[str, Any]]:
        team = self.get_team(team_id)
        if team is None:
            raise FileNotFoundError(f"Team '{team_id}' not found.")
        rows: list[dict[str, Any]] = list(team.get("messages", []))
        if run_id:
            rows = [row for row in rows if str(row.get("run_id")) == run_id]
        if channel:
            rows = [row for row in rows if str(row.get("channel")) == channel]
        rows.sort(key=lambda row: row.get("timestamp", 0))
        return rows[-max(1, limit):]

    def _write(self, team_id: str, payload: dict[str, Any], retries: int = 3, delay_seconds: float = 0.05) -> None:
        path = self._path(team_id)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        for attempt in range(retries + 1):
            try:
                path.write_text(text, encoding="utf-8")
                self._cache[team_id] = dict(payload)
                return
            except PermissionError:
                if attempt < retries:
                    time.sleep(delay_seconds)
                    continue
                # Keep runtime behavior working even if filesystem write is denied.
                self._cache[team_id] = dict(payload)
                return
            except Exception:
                self._cache[team_id] = dict(payload)
                return
