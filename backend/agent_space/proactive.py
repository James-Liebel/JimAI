"""Proactive run scheduler for Agent Space."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from .log_store import LogStore
from .paths import DATA_ROOT, ensure_layout
from .power import PowerManager

PROACTIVE_FILE = DATA_ROOT / "proactive_goals.json"
AUTO_SELF_IMPROVE_STATE_FILE = DATA_ROOT / "runtime" / "auto_self_improve_state.json"


class ProactiveEngine:
    """Runs configured proactive goals and self-improvement cycles."""

    def __init__(
        self,
        *,
        orchestrator: Any,
        power: PowerManager,
        logs: LogStore,
    ) -> None:
        ensure_layout()
        self.orchestrator = orchestrator
        self.power = power
        self.logs = logs
        self.running = False
        self._task: asyncio.Task | None = None
        self._last_tick = 0.0
        self._last_error = ""
        self._goals_override: list[dict[str, Any]] | None = None
        self._auto_failure_state = self._load_auto_failure_state()
        if not PROACTIVE_FILE.exists():
            self._save([])

    def _load(self) -> list[dict[str, Any]]:
        file_rows: list[dict[str, Any]] = []
        try:
            rows = json.loads(PROACTIVE_FILE.read_text(encoding="utf-8"))
            if isinstance(rows, list):
                file_rows = rows
        except Exception:
            file_rows = []
        if self._goals_override is not None:
            return [dict(row) for row in self._goals_override]
        return file_rows

    def _save(self, goals: list[dict[str, Any]], retries: int = 3, delay_seconds: float = 0.05) -> None:
        payload = json.dumps(goals, ensure_ascii=False, indent=2)
        for attempt in range(retries + 1):
            try:
                PROACTIVE_FILE.write_text(payload, encoding="utf-8")
                self._goals_override = None
                return
            except PermissionError:
                if attempt < retries:
                    time.sleep(delay_seconds)
                    continue
                self._goals_override = [dict(row) for row in goals]
                return
            except Exception:
                self._goals_override = [dict(row) for row in goals]
                return

    def _default_auto_failure_state(self) -> dict[str, Any]:
        return {
            "day": time.strftime("%Y-%m-%d", time.localtime()),
            "trigger_count_today": 0,
            "last_trigger_at": 0.0,
            "last_triggered_run_id": "",
            "last_auto_run_id": "",
            "handled_run_ids": [],
        }

    def _load_auto_failure_state(self) -> dict[str, Any]:
        state = self._default_auto_failure_state()
        if not AUTO_SELF_IMPROVE_STATE_FILE.exists():
            try:
                AUTO_SELF_IMPROVE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                AUTO_SELF_IMPROVE_STATE_FILE.write_text(
                    json.dumps(state, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                # Missing state file is expected on first boot; keep defaults.
                pass
            return state
        try:
            data = json.loads(AUTO_SELF_IMPROVE_STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                state.update(data)
        except Exception:
            logger.warning("Failed to load auto-failure state from file; using defaults", exc_info=True)
        if not isinstance(state.get("handled_run_ids"), list):
            state["handled_run_ids"] = []
        return state

    def _save_auto_failure_state(self) -> None:
        try:
            AUTO_SELF_IMPROVE_STATE_FILE.write_text(
                json.dumps(self._auto_failure_state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.warning("Failed to persist auto-failure state to disk", exc_info=True)

    def _refresh_auto_failure_day(self) -> None:
        today = time.strftime("%Y-%m-%d", time.localtime())
        if str(self._auto_failure_state.get("day") or "") == today:
            return
        self._auto_failure_state["day"] = today
        self._auto_failure_state["trigger_count_today"] = 0

    def _mark_run_handled(self, run_id: str) -> bool:
        rows = [str(item) for item in list(self._auto_failure_state.get("handled_run_ids") or []) if str(item).strip()]
        if run_id in rows:
            return False
        rows.append(run_id)
        self._auto_failure_state["handled_run_ids"] = rows[-400:]
        self._save_auto_failure_state()
        return True

    def _build_auto_failure_prompt(
        self,
        *,
        run: dict[str, Any],
        completion_summary: dict[str, Any],
    ) -> str:
        run_id = str(run.get("id") or "")
        objective = str(run.get("objective") or "").strip()
        status = str(run.get("status") or "").strip()
        error = str(run.get("error") or "").strip()
        summary_text = str(completion_summary.get("text") or "").strip()
        unresolved = int(completion_summary.get("failed_actions") or 0)
        recovered = int(completion_summary.get("recovered_actions") or 0)
        return (
            "Automatic self-healing request for jimAI.\n\n"
            f"Failed run id: {run_id}\n"
            f"Run status: {status}\n"
            f"Objective: {objective[:1200]}\n"
            f"Primary error: {error[:1200]}\n"
            f"Completion summary: {summary_text[:1600]}\n"
            f"Unresolved actions: {unresolved}\n"
            f"Recovered actions: {recovered}\n\n"
            "Task:\n"
            "1) Find root causes from this failure profile.\n"
            "2) Update the repository so this class of failure is less likely.\n"
            "3) Improve retries, fallback paths, and graceful degradation.\n"
            "4) Keep safety/review behavior intact.\n"
            "5) Produce reviewable diffs."
        )

    def list_goals(self, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._load()
        rows.sort(key=lambda row: row.get("updated_at", 0), reverse=True)
        return rows[: max(1, limit)]

    def add_goal(
        self,
        *,
        name: str,
        objective: str,
        interval_seconds: int = 900,
        enabled: bool = True,
        run_template: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        goals = self._load()
        now = time.time()
        row = {
            "id": str(uuid.uuid4()),
            "name": name or "Proactive Goal",
            "objective": objective,
            "interval_seconds": max(10, int(interval_seconds)),
            "enabled": bool(enabled),
            "run_template": run_template or {},
            "next_run_at": now,
            "last_run_at": None,
            "last_run_id": None,
            "created_at": now,
            "updated_at": now,
        }
        goals.append(row)
        self._save(goals)
        return row

    def update_goal(self, goal_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        goals = self._load()
        for row in goals:
            if str(row.get("id")) != goal_id:
                continue
            for key in ("name", "objective", "enabled", "run_template"):
                if key in updates:
                    row[key] = updates[key]
            if "interval_seconds" in updates:
                row["interval_seconds"] = max(10, int(updates["interval_seconds"]))
            if "next_run_at" in updates:
                row["next_run_at"] = float(updates["next_run_at"])
            row["updated_at"] = time.time()
            self._save(goals)
            return row
        raise FileNotFoundError(f"Goal '{goal_id}' not found.")

    def delete_goal(self, goal_id: str) -> bool:
        goals = self._load()
        kept = [row for row in goals if str(row.get("id")) != goal_id]
        if len(kept) == len(goals):
            return False
        self._save(kept)
        return True

    async def start(self) -> dict[str, Any]:
        if self.running and self._task and not self._task.done():
            return self.status()
        self.running = True
        self._task = asyncio.create_task(self._loop())
        return self.status()

    async def stop(self) -> dict[str, Any]:
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        return self.status()

    async def _loop(self) -> None:
        while self.running:
            try:
                await self.tick()
            except Exception as exc:
                self._last_error = str(exc)
            await asyncio.sleep(5.0)

    async def tick(self) -> dict[str, Any]:
        goals = self._load()
        now = time.time()
        triggered: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for goal in goals:
            if not bool(goal.get("enabled", True)):
                continue
            if float(goal.get("next_run_at", 0) or 0) > now:
                continue
            if not self.power.is_enabled():
                errors.append({"goal_id": goal["id"], "error": "power_off"})
                continue

            payload = dict(goal.get("run_template", {}))
            payload.setdefault("objective", str(goal.get("objective", "")))
            payload.setdefault("autonomous", True)
            payload.setdefault("review_gate", True)
            try:
                run = await self.orchestrator.start_run(payload)
                goal["last_run_at"] = now
                goal["last_run_id"] = run["id"]
                goal["next_run_at"] = now + max(10, int(goal.get("interval_seconds", 900)))
                goal["updated_at"] = now
                triggered.append({"goal_id": goal["id"], "run_id": run["id"]})
            except Exception as exc:
                goal["updated_at"] = now
                errors.append({"goal_id": goal["id"], "error": str(exc)})

        self._save(goals)
        self._last_tick = now
        self._last_error = errors[0]["error"] if errors else ""
        return {
            "triggered": triggered,
            "errors": errors,
            "checked": len(goals),
            "last_tick": self._last_tick,
        }

    async def run_self_improvement(
        self,
        *,
        prompt: str,
        confirmed_suggestions: list[str],
        auto_recovery: bool = False,
        parent_run_id: str = "",
    ) -> dict[str, Any]:
        cleaned_prompt = str(prompt or "").strip()
        suggestions = [str(item or "").strip() for item in confirmed_suggestions if str(item or "").strip()]
        settings = self.orchestrator.settings.get()
        retry_attempts = max(3, int(settings.get("subagent_retry_attempts", 2)))
        if not cleaned_prompt:
            raise ValueError("prompt is required for self-improvement runs.")
        if not suggestions:
            raise ValueError("At least one confirmed suggestion is required.")

        objective_lines = [
            "Run self-improvement analysis and propose updates",
            f"Mode: {'automatic failure recovery' if auto_recovery else 'manual request'}",
            "",
            "User improvement prompt:",
            cleaned_prompt,
            "",
            "Confirmed suggestions to execute:",
            *[f"- {item}" for item in suggestions],
        ]
        if auto_recovery and parent_run_id:
            objective_lines.extend(
                [
                    "",
                    f"Source failed run id: {parent_run_id}",
                ]
            )
        payload = {
            "objective": "\n".join(objective_lines).strip(),
            "autonomous": False,
            "review_gate": True,
            "subagent_retry_attempts": retry_attempts,
            "self_improve_prompt": cleaned_prompt,
            "confirmed_suggestions": suggestions,
            "auto_failure_self_improve_run": bool(auto_recovery),
            "auto_failure_parent_run_id": str(parent_run_id or "").strip(),
            "skip_auto_failure_self_improve": bool(auto_recovery),
            "subagents": [
                {
                    "id": "self-improver",
                    "role": "coder",
                    "depends_on": [],
                    "actions": [
                        {
                            "type": "self_improve",
                            "prompt": cleaned_prompt,
                            "confirmed_suggestions": suggestions,
                        }
                    ],
                }
            ],
        }
        return await self.orchestrator.start_run(payload)

    async def handle_run_completion(
        self,
        run: dict[str, Any],
        payload: dict[str, Any],
        completion_summary: dict[str, Any],
    ) -> dict[str, Any] | None:
        cfg = self.orchestrator.settings.get()
        if not bool(cfg.get("auto_self_improve_on_failure_enabled", True)):
            return None

        status = str(run.get("status") or "").strip().lower()
        include_stopped = bool(cfg.get("auto_self_improve_on_failure_include_stopped", False))
        eligible = status == "failed" or (include_stopped and status == "stopped")
        if not eligible:
            return None

        if bool(payload.get("auto_failure_self_improve_run")):
            return {"triggered": False, "reason": "already_auto_recovery_run"}
        if bool(payload.get("skip_auto_failure_self_improve")):
            return {"triggered": False, "reason": "skip_flag"}
        if not self.power.is_enabled():
            return {"triggered": False, "reason": "power_off"}

        run_id = str(run.get("id") or "").strip()
        if not run_id:
            return {"triggered": False, "reason": "missing_run_id"}
        if not self._mark_run_handled(run_id):
            return {"triggered": False, "reason": "already_handled", "run_id": run_id}

        self._refresh_auto_failure_day()
        now = time.time()
        cooldown_seconds = max(0, int(cfg.get("auto_self_improve_on_failure_cooldown_seconds", 180)))
        max_per_day = max(0, int(cfg.get("auto_self_improve_on_failure_max_per_day", 12)))
        since_last = now - float(self._auto_failure_state.get("last_trigger_at") or 0.0)
        if cooldown_seconds > 0 and since_last < cooldown_seconds:
            return {
                "triggered": False,
                "reason": "cooldown",
                "run_id": run_id,
                "cooldown_seconds": cooldown_seconds,
                "retry_after_seconds": max(1, int(cooldown_seconds - since_last)),
            }
        if max_per_day >= 0 and int(self._auto_failure_state.get("trigger_count_today") or 0) >= max_per_day:
            return {"triggered": False, "reason": "daily_cap", "run_id": run_id, "max_per_day": max_per_day}

        prompt = self._build_auto_failure_prompt(run=run, completion_summary=completion_summary)
        suggestions = [
            "Harden failure path with bounded retries and deterministic fallback behavior.",
            "Improve observability so future failures include actionable root-cause details.",
            "Keep review-gated safety and rollback support intact while fixing this issue class.",
        ]
        try:
            queued = await self.run_self_improvement(
                prompt=prompt,
                confirmed_suggestions=suggestions,
                auto_recovery=True,
                parent_run_id=run_id,
            )
        except Exception as exc:
            self._last_error = str(exc)
            return {"triggered": False, "reason": "queue_failed", "run_id": run_id, "error": str(exc)}

        self._auto_failure_state["last_trigger_at"] = now
        self._auto_failure_state["last_triggered_run_id"] = run_id
        self._auto_failure_state["last_auto_run_id"] = str(queued.get("id") or "")
        self._auto_failure_state["trigger_count_today"] = int(self._auto_failure_state.get("trigger_count_today") or 0) + 1
        self._save_auto_failure_state()
        return {
            "triggered": True,
            "reason": "queued",
            "run_id": run_id,
            "auto_run_id": queued.get("id"),
            "trigger_count_today": int(self._auto_failure_state.get("trigger_count_today") or 0),
        }

    def status(self) -> dict[str, Any]:
        self._refresh_auto_failure_day()
        return {
            "running": self.running,
            "goal_count": len(self._load()),
            "last_tick": self._last_tick,
            "last_error": self._last_error,
            "auto_self_improve_on_failure": {
                "day": str(self._auto_failure_state.get("day") or ""),
                "trigger_count_today": int(self._auto_failure_state.get("trigger_count_today") or 0),
                "last_trigger_at": float(self._auto_failure_state.get("last_trigger_at") or 0.0),
                "last_triggered_run_id": str(self._auto_failure_state.get("last_triggered_run_id") or ""),
                "last_auto_run_id": str(self._auto_failure_state.get("last_auto_run_id") or ""),
            },
        }
