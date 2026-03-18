"""App instance tracking and Ollama lifecycle management."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import subprocess
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

from models import ollama_client

from .paths import RUNTIME_DIR, ensure_layout

STATE_FILE = RUNTIME_DIR / "instances.json"


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_pid(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            return result.returncode == 0
        os.kill(pid, signal.SIGTERM)
        return True
    except Exception:
        return False


class InstanceLifecycleManager:
    """Tracks active app instances and starts/stops Ollama accordingly."""

    def __init__(
        self,
        *,
        instance_ttl_seconds: int = 45,
        stop_grace_seconds: int = 12,
        cleanup_interval_seconds: int = 5,
    ) -> None:
        ensure_layout()
        self._lock = asyncio.Lock()
        self._instances: dict[str, dict[str, Any]] = {}
        self._instance_ttl_seconds = max(10, int(instance_ttl_seconds))
        self._stop_grace_seconds = max(1, int(stop_grace_seconds))
        self._cleanup_interval_seconds = max(1, int(cleanup_interval_seconds))
        self._pending_stop_at: float | None = None
        self._managed_ollama_pid: int | None = None
        self._last_ollama_error = ""
        self._last_ollama_start_at = 0.0
        self._running = False
        self._task: asyncio.Task | None = None
        self._load_state()

    def _load_state(self) -> None:
        if not STATE_FILE.exists():
            self._persist_state_locked()
            return
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        instances = data.get("instances")
        if isinstance(instances, dict):
            for instance_id, row in instances.items():
                if not isinstance(row, dict):
                    continue
                key = str(instance_id or "").strip()
                if not key:
                    continue
                self._instances[key] = {
                    "instance_id": key,
                    "client": str(row.get("client") or "ui"),
                    "metadata": dict(row.get("metadata") or {}),
                    "created_at": float(row.get("created_at") or time.time()),
                    "last_seen_at": float(row.get("last_seen_at") or time.time()),
                }
        managed_pid = int(data.get("managed_ollama_pid") or 0)
        self._managed_ollama_pid = managed_pid if managed_pid > 0 else None
        self._pending_stop_at = float(data["pending_stop_at"]) if data.get("pending_stop_at") else None
        self._last_ollama_error = str(data.get("last_ollama_error") or "")
        self._last_ollama_start_at = float(data.get("last_ollama_start_at") or 0.0)
        self._persist_state_locked()

    def _persist_state_locked(self) -> None:
        payload = {
            "instances": self._instances,
            "instance_ttl_seconds": self._instance_ttl_seconds,
            "stop_grace_seconds": self._stop_grace_seconds,
            "pending_stop_at": self._pending_stop_at,
            "managed_ollama_pid": self._managed_ollama_pid,
            "last_ollama_error": self._last_ollama_error,
            "last_ollama_start_at": self._last_ollama_start_at,
            "updated_at": time.time(),
        }
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.warning("Failed to persist instance lifecycle state to disk", exc_info=True)

    async def startup(self) -> None:
        if self._running and self._task and not self._task.done():
            return
        await self.tick()
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def shutdown(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        await self._stop_managed_ollama()

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.tick()
            except Exception:
                logger.warning("Unhandled error in instance lifecycle loop tick", exc_info=True)
            await asyncio.sleep(self._cleanup_interval_seconds)

    def _prune_expired_locked(self, now: float) -> list[str]:
        stale_ids: list[str] = []
        for instance_id, row in list(self._instances.items()):
            last_seen = float(row.get("last_seen_at") or 0.0)
            if now - last_seen > self._instance_ttl_seconds:
                stale_ids.append(instance_id)
                self._instances.pop(instance_id, None)
        if stale_ids and not self._instances and self._pending_stop_at is None:
            self._pending_stop_at = now + self._stop_grace_seconds
        return stale_ids

    async def tick(self) -> dict[str, Any]:
        now = time.time()
        should_stop = False
        stale_ids: list[str] = []
        async with self._lock:
            stale_ids = self._prune_expired_locked(now)
            if not self._instances and self._pending_stop_at and now >= self._pending_stop_at:
                self._pending_stop_at = None
                should_stop = True
            if self._managed_ollama_pid and not _pid_running(int(self._managed_ollama_pid)):
                self._managed_ollama_pid = None
            self._persist_state_locked()
        if should_stop:
            await self._stop_managed_ollama()
        return {"stale_instances": stale_ids, "active_instances": len(self._instances)}

    async def _can_reach_ollama(self) -> bool:
        try:
            await ollama_client.list_models()
            return True
        except Exception:
            return False

    async def _start_ollama(self) -> dict[str, Any]:
        if await self._can_reach_ollama():
            return {"ollama_running": True, "ollama_started": False, "error": ""}
        ollama_bin = shutil.which("ollama")
        if not ollama_bin:
            error = "Ollama executable not found in PATH."
            async with self._lock:
                self._last_ollama_error = error
                self._persist_state_locked()
            return {"ollama_running": False, "ollama_started": False, "error": error}

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        try:
            proc = subprocess.Popen(
                [ollama_bin, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except Exception as exc:
            error = f"Failed to start Ollama: {exc}"
            async with self._lock:
                self._last_ollama_error = error
                self._persist_state_locked()
            return {"ollama_running": False, "ollama_started": False, "error": error}

        deadline = time.time() + 30.0
        while time.time() < deadline:
            if await self._can_reach_ollama():
                async with self._lock:
                    self._managed_ollama_pid = int(proc.pid)
                    self._last_ollama_error = ""
                    self._last_ollama_start_at = time.time()
                    self._persist_state_locked()
                return {
                    "ollama_running": True,
                    "ollama_started": True,
                    "managed_ollama_pid": int(proc.pid),
                    "error": "",
                }
            await asyncio.sleep(0.5)

        _kill_pid(int(proc.pid))
        error = "Timed out waiting for Ollama to start."
        async with self._lock:
            self._last_ollama_error = error
            self._persist_state_locked()
        return {"ollama_running": False, "ollama_started": False, "error": error}

    async def _stop_managed_ollama(self) -> dict[str, Any]:
        async with self._lock:
            pid = int(self._managed_ollama_pid or 0)
            self._managed_ollama_pid = None
            self._persist_state_locked()
        if not pid:
            return {"ollama_stopped": False, "managed_ollama_pid": None}
        stopped = _kill_pid(pid)
        return {"ollama_stopped": bool(stopped), "managed_ollama_pid": pid}

    async def register_instance(
        self,
        *,
        instance_id: str = "",
        client: str = "ui",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = time.time()
        normalized_id = str(instance_id or "").strip() or str(uuid.uuid4())
        normalized_client = str(client or "ui").strip() or "ui"
        normalized_metadata = dict(metadata or {})

        should_start = False
        async with self._lock:
            self._prune_expired_locked(now)
            prev_count = len(self._instances)
            row = self._instances.get(normalized_id) or {
                "instance_id": normalized_id,
                "created_at": now,
            }
            row["client"] = normalized_client
            row["metadata"] = normalized_metadata
            row["last_seen_at"] = now
            self._instances[normalized_id] = row
            self._pending_stop_at = None
            should_start = prev_count == 0
            self._persist_state_locked()

        start_info: dict[str, Any] = {}
        if should_start:
            start_info = await self._start_ollama()
        status = await self.status()
        return {"instance_id": normalized_id, "registered": True, **status, **start_info}

    async def heartbeat(
        self,
        *,
        instance_id: str,
        client: str = "ui",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_id = str(instance_id or "").strip()
        if not normalized_id:
            raise ValueError("instance_id is required")
        now = time.time()
        normalized_client = str(client or "ui").strip() or "ui"
        normalized_metadata = dict(metadata or {})

        should_start = False
        async with self._lock:
            self._prune_expired_locked(now)
            prev_count = len(self._instances)
            existed = normalized_id in self._instances
            row = self._instances.get(normalized_id) or {
                "instance_id": normalized_id,
                "created_at": now,
            }
            row["client"] = normalized_client
            row["metadata"] = normalized_metadata or row.get("metadata", {})
            row["last_seen_at"] = now
            self._instances[normalized_id] = row
            self._pending_stop_at = None
            should_start = prev_count == 0
            self._persist_state_locked()

        start_info: dict[str, Any] = {}
        if should_start:
            start_info = await self._start_ollama()
        status = await self.status()
        return {
            "instance_id": normalized_id,
            "heartbeat": True,
            "recovered_registration": not existed,
            **status,
            **start_info,
        }

    async def unregister_instance(self, *, instance_id: str, reason: str = "") -> dict[str, Any]:
        normalized_id = str(instance_id or "").strip()
        now = time.time()
        existed = False
        async with self._lock:
            self._prune_expired_locked(now)
            existed = normalized_id in self._instances
            if existed:
                self._instances.pop(normalized_id, None)
            if not self._instances:
                self._pending_stop_at = now + self._stop_grace_seconds
            self._persist_state_locked()
        await self.tick()
        status = await self.status()
        return {"instance_id": normalized_id, "unregistered": existed, "reason": reason or "", **status}

    async def status(self) -> dict[str, Any]:
        now = time.time()
        async with self._lock:
            self._prune_expired_locked(now)
            if self._managed_ollama_pid and not _pid_running(int(self._managed_ollama_pid)):
                self._managed_ollama_pid = None
            snapshot = [
                {
                    "instance_id": instance_id,
                    "client": str(row.get("client") or "ui"),
                    "created_at": float(row.get("created_at") or now),
                    "last_seen_at": float(row.get("last_seen_at") or now),
                    "age_seconds": max(0.0, now - float(row.get("last_seen_at") or now)),
                }
                for instance_id, row in self._instances.items()
            ]
            snapshot.sort(key=lambda row: row["last_seen_at"], reverse=True)
            pending_stop_at = self._pending_stop_at
            managed_pid = int(self._managed_ollama_pid or 0) or None
            last_error = self._last_ollama_error
            self._persist_state_locked()

        ollama_running = await self._can_reach_ollama()
        return {
            "active_instances": len(snapshot),
            "instances": snapshot,
            "instance_ttl_seconds": self._instance_ttl_seconds,
            "stop_grace_seconds": self._stop_grace_seconds,
            "pending_stop_at": pending_stop_at,
            "managed_ollama_pid": managed_pid,
            "ollama_running": bool(ollama_running),
            "last_ollama_error": last_error,
            "last_ollama_start_at": self._last_ollama_start_at,
        }
