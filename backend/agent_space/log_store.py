"""Action logs and metrics store for observability."""

from __future__ import annotations

import json
import logging
import time
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

from .paths import LOGS_DIR, ensure_layout

ACTIONS_LOG_FILE = LOGS_DIR / "actions.jsonl"
EVENTS_LOG_FILE = LOGS_DIR / "events.jsonl"
METRICS_FILE = LOGS_DIR / "metrics.json"

DEFAULT_METRICS = {
    "runs_started": 0,
    "runs_completed": 0,
    "runs_failed": 0,
    "runs_stopped": 0,
    "actions_total": 0,
    "actions_failed": 0,
    "reviews_created": 0,
    "reviews_applied": 0,
    "rollbacks": 0,
}


class LogStore:
    """Persistent JSONL logger with simple counters."""

    def __init__(self) -> None:
        ensure_layout()
        self._lock = Lock()
        self._metrics_override = dict(DEFAULT_METRICS)
        self._action_buffer: list[dict[str, Any]] = []
        self._event_buffer: list[dict[str, Any]] = []
        if METRICS_FILE.exists():
            try:
                self._metrics_override.update(json.loads(METRICS_FILE.read_text(encoding="utf-8")))
            except Exception:
                logger.warning("Failed to load persisted metrics from file", exc_info=True)
        else:
            self._persist_metrics(self._metrics_override)

    def _append_jsonl(
        self,
        path: Any,
        payload: dict[str, Any],
        retries: int = 2,
        delay_seconds: float = 0.05,
    ) -> bool:
        for attempt in range(retries + 1):
            try:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
                return True
            except PermissionError:
                if attempt < retries:
                    time.sleep(delay_seconds)
                    continue
                return False
            except Exception:
                return False
        return False

    def _persist_metrics(self, metrics: dict[str, int], retries: int = 2, delay_seconds: float = 0.05) -> bool:
        payload = json.dumps(metrics, indent=2)
        for attempt in range(retries + 1):
            try:
                METRICS_FILE.write_text(payload, encoding="utf-8")
                self._metrics_override = dict(metrics)
                return True
            except PermissionError:
                if attempt < retries:
                    time.sleep(delay_seconds)
                    continue
                self._metrics_override = dict(metrics)
                return False
            except Exception:
                self._metrics_override = dict(metrics)
                return False
        self._metrics_override = dict(metrics)
        return False

    def log_action(self, run_id: str, agent_id: str, action: dict[str, Any], result: dict[str, Any]) -> None:
        entry = {
            "ts": time.time(),
            "run_id": run_id,
            "agent_id": agent_id,
            "action": action,
            "result": result,
        }
        with self._lock:
            if not self._append_jsonl(ACTIONS_LOG_FILE, entry):
                self._action_buffer.append(entry)
                self._action_buffer = self._action_buffer[-2000:]
            self.increment("actions_total", 1)
            if not result.get("success", True):
                self.increment("actions_failed", 1)

    def log_event(self, run_id: str, event: dict[str, Any]) -> None:
        entry = {
            "ts": time.time(),
            "run_id": run_id,
            "event": event,
        }
        with self._lock:
            if not self._append_jsonl(EVENTS_LOG_FILE, entry):
                self._event_buffer.append(entry)
                self._event_buffer = self._event_buffer[-2000:]

    def increment(self, key: str, by: int = 1) -> None:
        metrics = self.get_metrics()
        metrics[key] = int(metrics.get(key, 0)) + by
        self._persist_metrics(metrics)

    def get_metrics(self) -> dict[str, int]:
        try:
            file_metrics = json.loads(METRICS_FILE.read_text(encoding="utf-8"))
            if isinstance(file_metrics, dict):
                merged = dict(DEFAULT_METRICS)
                merged.update(file_metrics)
                merged.update(self._metrics_override)
                return merged
        except Exception:
            logger.warning("Failed to read metrics file; falling back to in-memory values", exc_info=True)
        return dict(self._metrics_override)

    def list_action_logs(self, limit: int = 200, run_id: str | None = None) -> list[dict[str, Any]]:
        lines: list[str] = []
        if ACTIONS_LOG_FILE.exists():
            try:
                lines = ACTIONS_LOG_FILE.read_text(encoding="utf-8").splitlines()
            except Exception:
                lines = []
        rows: list[dict[str, Any]] = []
        source_lines = lines if run_id else lines[-max(1, limit) :]
        for line in source_lines:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        buf = list(self._action_buffer)
        if not run_id:
            buf = buf[-max(1, limit) :]
        rows.extend(buf)
        if run_id:
            rid = str(run_id).strip()
            rows = [r for r in rows if str(r.get("run_id", "")).strip() == rid]
        rows.sort(key=lambda r: float(r.get("ts", 0) or 0))
        return rows[-max(1, limit) :]
