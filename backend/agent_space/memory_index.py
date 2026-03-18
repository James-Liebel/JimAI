"""Local code indexing and run-memory summaries."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from .paths import INDEX_DIR, MEMORY_DIR, PROJECT_ROOT, ensure_layout

CODE_INDEX_FILE = INDEX_DIR / "code_index.json"
RUN_MEMORY_FILE = MEMORY_DIR / "run_memory.json"

IGNORED_DIR_NAMES = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    "chroma_db",
}

TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".txt",
    ".css",
    ".html",
    ".yml",
    ".yaml",
    ".sh",
    ".ps1",
}


class MemoryIndexStore:
    """Holds code index and recent run summaries."""

    def __init__(self) -> None:
        ensure_layout()
        self._run_memory_override: list[dict[str, Any]] = []
        self._code_index_override: dict[str, Any] | None = None
        if not RUN_MEMORY_FILE.exists():
            self._persist_json(RUN_MEMORY_FILE, self._run_memory_override)
        else:
            try:
                rows = json.loads(RUN_MEMORY_FILE.read_text(encoding="utf-8"))
                if isinstance(rows, list):
                    self._run_memory_override = rows
            except Exception:
                logger.warning("Failed to load run memory index from file", exc_info=True)

    def _persist_json(self, path: Path, payload: Any, retries: int = 2, delay_seconds: float = 0.05) -> bool:
        data = json.dumps(payload, ensure_ascii=False, indent=2)
        for attempt in range(retries + 1):
            try:
                path.write_text(data, encoding="utf-8")
                return True
            except PermissionError:
                if attempt < retries:
                    time.sleep(delay_seconds)
                    continue
                return False
            except Exception:
                return False
        return False

    def rebuild_code_index(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for path in PROJECT_ROOT.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(PROJECT_ROOT)
            if any(part in IGNORED_DIR_NAMES for part in rel.parts):
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            items.append(
                {
                    "path": rel.as_posix(),
                    "mtime": path.stat().st_mtime,
                    "size": path.stat().st_size,
                    "excerpt": text[:4000],
                }
            )
        payload = {
            "created_at": time.time(),
            "count": len(items),
            "items": items,
        }
        self._persist_json(CODE_INDEX_FILE, payload)
        self._code_index_override = payload
        return {
            "indexed_files": len(items),
            "created_at": payload["created_at"],
        }

    def search_code_index(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        data: dict[str, Any] = {}
        if CODE_INDEX_FILE.exists():
            try:
                loaded = json.loads(CODE_INDEX_FILE.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                data = {}
        if not data:
            if self._code_index_override:
                data = self._code_index_override
            else:
                self.rebuild_code_index()
                data = self._code_index_override or {}
        q = (query or "").strip().lower()
        if not q:
            return []
        rows: list[dict[str, Any]] = []
        for item in data.get("items", []):
            path = str(item.get("path", ""))
            excerpt = str(item.get("excerpt", ""))
            path_lower = path.lower()
            excerpt_lower = excerpt.lower()
            if q not in path_lower and q not in excerpt_lower:
                continue
            score = 0
            if q in path_lower:
                score += 10
            score += excerpt_lower.count(q)
            rows.append(
                {
                    "path": path,
                    "score": score,
                    "excerpt": excerpt[:500],
                }
            )
        rows.sort(key=lambda x: x["score"], reverse=True)
        return rows[: max(1, limit)]

    def add_run_memory(self, summary: dict[str, Any]) -> None:
        rows = self.list_recent_runs(limit=500)
        rows.insert(0, summary)
        rows = rows[:200]
        if not self._persist_json(RUN_MEMORY_FILE, rows):
            self._run_memory_override = rows
        else:
            self._run_memory_override = rows

    def list_recent_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        try:
            rows = json.loads(RUN_MEMORY_FILE.read_text(encoding="utf-8"))
            if isinstance(rows, list):
                self._run_memory_override = rows
            else:
                rows = list(self._run_memory_override)
        except Exception:
            rows = list(self._run_memory_override)
        return rows[: max(1, limit)]
