"""Heartbeat-driven autonomous scheduler.

OpenClaw / arXiv:2604.14178 ("Heartbeat-Driven Autonomous Thinking Activity
Scheduling") formalised a pattern that 2026 agent platforms have widely
adopted: a periodic tick wakes the agent regardless of external events and
asks "given your goals, your memory, and pending tasks, what should you do
right now?" Combined with a tool that lets the agent schedule its own future
wake-ups, this is the cheapest single change that moves an agent from
"reactive responder" to "proactive actor".

This scheduler is intentionally minimal:
    * jobs persist as JSON
    * a tick loop runs every ``tick_interval_seconds``
    * each tick fires due jobs by calling the orchestrator
    * agents can schedule their own follow-ups via ``schedule_self``
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from ..paths import DATA_ROOT

logger = logging.getLogger(__name__)

HEARTBEAT_DIR = DATA_ROOT / "autonomy"
JOBS_FILE = HEARTBEAT_DIR / "heartbeat_jobs.json"

DEFAULT_TICK_SECONDS = 60.0
MIN_INTERVAL_SECONDS = 30.0


@dataclass
class HeartbeatJob:
    id: str
    name: str
    objective: str
    interval_seconds: float
    next_fire_at: float
    enabled: bool = True
    one_shot: bool = False
    created_at: float = 0.0
    last_fired_at: float = 0.0
    fire_count: int = 0
    last_error: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "HeartbeatJob":
        return cls(
            id=str(row.get("id") or uuid.uuid4().hex),
            name=str(row.get("name") or "heartbeat-job"),
            objective=str(row.get("objective") or ""),
            interval_seconds=max(MIN_INTERVAL_SECONDS, float(row.get("interval_seconds") or 900.0)),
            next_fire_at=float(row.get("next_fire_at") or time.time()),
            enabled=bool(row.get("enabled", True)),
            one_shot=bool(row.get("one_shot", False)),
            created_at=float(row.get("created_at") or time.time()),
            last_fired_at=float(row.get("last_fired_at") or 0.0),
            fire_count=int(row.get("fire_count") or 0),
            last_error=str(row.get("last_error") or ""),
            payload=dict(row.get("payload") or {}),
            metadata=dict(row.get("metadata") or {}),
        )


JobAction = Callable[[HeartbeatJob], Awaitable[dict[str, Any] | None]]


class HeartbeatScheduler:
    """Tick-driven job runner with self-callable scheduling."""

    def __init__(
        self,
        *,
        action: JobAction,
        file_path: Path = JOBS_FILE,
        tick_interval_seconds: float = DEFAULT_TICK_SECONDS,
    ) -> None:
        self.action = action
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.tick_interval_seconds = max(5.0, float(tick_interval_seconds))
        self._jobs: dict[str, HeartbeatJob] = {}
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_tick_at = 0.0
        self._last_tick_fired = 0
        self._last_error = ""
        self._loaded = False

    # ------------------------------------------------------------------ load

    def _load(self) -> None:
        if self._loaded:
            return
        if not self.file_path.exists():
            self._loaded = True
            return
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read heartbeat jobs: %s", exc)
            data = []
        if isinstance(data, list):
            for row in data:
                if not isinstance(row, dict):
                    continue
                job = HeartbeatJob.from_dict(row)
                self._jobs[job.id] = job
        self._loaded = True

    def _save_locked(self) -> None:
        try:
            self.file_path.write_text(
                json.dumps([job.to_dict() for job in self._jobs.values()], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to write heartbeat jobs: %s", exc)

    # --------------------------------------------------------------- control

    async def start(self) -> dict[str, Any]:
        async with self._lock:
            self._load()
            if self._running and self._task and not self._task.done():
                return self.status()
            self._running = True
            self._task = asyncio.create_task(self._loop())
            return self.status()

    async def stop(self) -> dict[str, Any]:
        async with self._lock:
            self._running = False
            task = self._task
            self._task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        return self.status()

    async def _loop(self) -> None:
        try:
            while self._running:
                try:
                    await self.tick()
                except Exception as exc:
                    self._last_error = str(exc)
                    logger.exception("heartbeat tick error: %s", exc)
                await asyncio.sleep(self.tick_interval_seconds)
        except asyncio.CancelledError:
            return

    # ----------------------------------------------------------------- ticks

    async def tick(self) -> dict[str, Any]:
        async with self._lock:
            self._load()
            now = time.time()
            due: list[HeartbeatJob] = [
                job for job in self._jobs.values()
                if job.enabled and job.next_fire_at <= now
            ]
        fired = 0
        errors: list[dict[str, Any]] = []
        for job in due:
            try:
                result = await self.action(job)
                async with self._lock:
                    job.last_fired_at = time.time()
                    job.fire_count += 1
                    job.last_error = ""
                    if isinstance(result, dict):
                        job.metadata["last_result"] = {
                            k: v for k, v in result.items() if k in {"id", "status", "run_id"}
                        }
                    if job.one_shot:
                        self._jobs.pop(job.id, None)
                    else:
                        job.next_fire_at = time.time() + job.interval_seconds
                    self._save_locked()
                fired += 1
            except Exception as exc:
                async with self._lock:
                    job.last_error = str(exc)[:600]
                    job.next_fire_at = time.time() + max(60.0, job.interval_seconds * 0.5)
                    self._save_locked()
                errors.append({"job_id": job.id, "error": str(exc)})
                logger.warning("heartbeat job %s failed: %s", job.id, exc)
        async with self._lock:
            self._last_tick_at = time.time()
            self._last_tick_fired = fired
            if errors:
                self._last_error = errors[0]["error"]
        return {"due": len(due), "fired": fired, "errors": errors, "tick_at": self._last_tick_at}

    # ------------------------------------------------------------------ jobs

    async def add_job(
        self,
        *,
        name: str,
        objective: str,
        interval_seconds: float = 900.0,
        one_shot: bool = False,
        first_fire_in_seconds: float | None = None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> HeartbeatJob:
        async with self._lock:
            self._load()
            now = time.time()
            interval = max(MIN_INTERVAL_SECONDS, float(interval_seconds))
            first_delay = float(first_fire_in_seconds) if first_fire_in_seconds is not None else interval
            first_delay = max(0.0, first_delay)
            job = HeartbeatJob(
                id=uuid.uuid4().hex,
                name=name.strip() or "heartbeat-job",
                objective=objective.strip(),
                interval_seconds=interval,
                next_fire_at=now + first_delay,
                enabled=bool(enabled),
                one_shot=bool(one_shot),
                created_at=now,
                payload=dict(payload or {}),
                metadata=dict(metadata or {}),
            )
            self._jobs[job.id] = job
            self._save_locked()
            return job

    async def schedule_self(
        self,
        *,
        agent_id: str,
        objective: str,
        when_in_seconds: float,
        payload: dict[str, Any] | None = None,
    ) -> HeartbeatJob:
        """Tool-style entrypoint: an agent schedules its own future wake-up."""
        return await self.add_job(
            name=f"self:{agent_id}:{objective[:24]}",
            objective=objective,
            interval_seconds=max(MIN_INTERVAL_SECONDS, when_in_seconds),
            one_shot=True,
            first_fire_in_seconds=when_in_seconds,
            payload=dict(payload or {}),
            metadata={"scheduled_by": agent_id, "self_scheduled": True},
        )

    async def update_job(self, job_id: str, updates: dict[str, Any]) -> HeartbeatJob:
        async with self._lock:
            self._load()
            job = self._jobs.get(job_id)
            if job is None:
                raise FileNotFoundError(f"heartbeat job '{job_id}' not found")
            if "name" in updates:
                job.name = str(updates["name"]).strip() or job.name
            if "objective" in updates:
                job.objective = str(updates["objective"]).strip()
            if "interval_seconds" in updates:
                job.interval_seconds = max(MIN_INTERVAL_SECONDS, float(updates["interval_seconds"]))
            if "next_fire_at" in updates:
                job.next_fire_at = float(updates["next_fire_at"])
            if "enabled" in updates:
                job.enabled = bool(updates["enabled"])
            if "payload" in updates and isinstance(updates["payload"], dict):
                job.payload = dict(updates["payload"])
            self._save_locked()
            return job

    async def delete_job(self, job_id: str) -> bool:
        async with self._lock:
            self._load()
            if job_id not in self._jobs:
                return False
            self._jobs.pop(job_id, None)
            self._save_locked()
            return True

    def list_jobs(self) -> list[HeartbeatJob]:
        self._load()
        rows = list(self._jobs.values())
        rows.sort(key=lambda j: (j.enabled, -j.next_fire_at), reverse=True)
        return rows

    def status(self) -> dict[str, Any]:
        self._load()
        return {
            "running": self._running,
            "tick_interval_seconds": self.tick_interval_seconds,
            "job_count": len(self._jobs),
            "enabled_count": sum(1 for j in self._jobs.values() if j.enabled),
            "last_tick_at": self._last_tick_at,
            "last_tick_fired": self._last_tick_fired,
            "last_error": self._last_error,
        }
