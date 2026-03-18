"""Snapshot and rollback support for Agent Space."""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .paths import PROJECT_ROOT, SNAPSHOTS_DIR, ensure_layout


class SnapshotStore:
    """Stores pre-change snapshots for rollback."""

    def __init__(self) -> None:
        ensure_layout()
        self._cache: dict[str, dict[str, Any]] = {}

    def _path(self, snapshot_id: str) -> Path:
        return SNAPSHOTS_DIR / f"{snapshot_id}.json"

    def create_snapshot(
        self,
        *,
        run_id: str,
        note: str,
        files: list[dict[str, Any]],
        create_git_checkpoint: bool = False,
    ) -> dict[str, Any]:
        snapshot_id = str(uuid.uuid4())
        git_checkpoint_branch: str | None = None
        if create_git_checkpoint:
            git_checkpoint_branch = self._create_git_checkpoint(snapshot_id)

        payload = {
            "id": snapshot_id,
            "run_id": run_id,
            "note": note,
            "created_at": time.time(),
            "files": files,
            "git_checkpoint_branch": git_checkpoint_branch,
        }
        self._write(payload)
        return payload

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        cached = self._cache.get(snapshot_id)
        if cached is not None:
            return dict(cached)
        path = self._path(snapshot_id)
        if not path.exists():
            return None
        row = json.loads(path.read_text(encoding="utf-8"))
        self._cache[snapshot_id] = dict(row)
        return row

    def list_snapshots(self, limit: int = 100) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        for path in SNAPSHOTS_DIR.glob("*.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
                snapshots.append(row)
                snapshot_id = str(row.get("id", ""))
                if snapshot_id:
                    self._cache[snapshot_id] = dict(row)
            except Exception:
                continue
        for cached in self._cache.values():
            if not any(str(row.get("id")) == str(cached.get("id")) for row in snapshots):
                snapshots.append(dict(cached))
        snapshots.sort(key=lambda row: row.get("created_at", 0), reverse=True)
        return snapshots[: max(1, limit)]

    def restore_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        data = self.get_snapshot(snapshot_id)
        if data is None:
            raise FileNotFoundError(f"Snapshot '{snapshot_id}' was not found.")
        restored_files = 0
        for entry in data.get("files", []):
            rel_path = str(entry.get("path", "")).replace("\\", "/")
            target = (PROJECT_ROOT / rel_path).resolve()
            if not str(target).startswith(str(PROJECT_ROOT.resolve())):
                continue
            existed = bool(entry.get("existed_before", False))
            old_content = entry.get("old_content")
            if existed:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(old_content or "", encoding="utf-8")
                restored_files += 1
            else:
                if target.exists():
                    target.unlink()
                    restored_files += 1

        return {
            "snapshot_id": snapshot_id,
            "restored_files": restored_files,
            "run_id": data.get("run_id"),
            "git_checkpoint_branch": data.get("git_checkpoint_branch"),
        }

    def _write(self, snapshot: dict[str, Any], retries: int = 3, delay_seconds: float = 0.05) -> None:
        snapshot_id = str(snapshot["id"])
        payload = json.dumps(snapshot, indent=2)
        path = self._path(snapshot_id)
        for attempt in range(retries + 1):
            try:
                path.write_text(payload, encoding="utf-8")
                self._cache[snapshot_id] = dict(snapshot)
                return
            except PermissionError:
                if attempt < retries:
                    time.sleep(delay_seconds)
                    continue
                self._cache[snapshot_id] = dict(snapshot)
                return
            except Exception:
                self._cache[snapshot_id] = dict(snapshot)
                return

    def _create_git_checkpoint(self, snapshot_id: str) -> str | None:
        try:
            check = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if check.returncode != 0:
                return None
            branch = f"agent-space/checkpoint-{snapshot_id[:8]}"
            create = subprocess.run(
                ["git", "branch", branch],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if create.returncode == 0:
                return branch
        except Exception:
            return None
        return None
