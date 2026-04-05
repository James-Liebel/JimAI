"""Agent Space orchestrator: runs autonomous/subagent workflows."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

from models import ollama_client

from .chat_store import AgentSpaceChatStore
from .config import SettingsStore
from .exporter import export_items
from .log_store import LogStore
from .memory_index import MemoryIndexStore
from .paths import DATA_ROOT, PROJECT_ROOT
from .policies import PolicyError, run_command
from .power import PowerManager
from .review_store import ReviewStore
from .snapshot_store import SnapshotStore
from .skill_store import SkillStore
from .team_store import TeamStore
from .web_research import fetch_web, search_web
from . import orch_helpers, orch_planning
from config.settings import BROWSER_EXTRACT_MAX_CHARS


def _now() -> float:
    return time.time()


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": run["id"],
        "status": run["status"],
        "objective": run["objective"],
        "created_at": run["created_at"],
        "updated_at": run["updated_at"],
        "started_at": run.get("started_at"),
        "ended_at": run.get("ended_at"),
        "review_ids": run.get("review_ids", []),
        "snapshot_ids": run.get("snapshot_ids", []),
        "action_count": run.get("action_count", 0),
        "error": run.get("error"),
        "team_id": run.get("team_id"),
        "team_name": run.get("team_name"),
        "skills": list(run.get("skills") or []),
        "message_count": len(run.get("messages", [])),
        "completion_summary": run.get("completion_summary"),
        "review_scope": str(run.get("review_scope") or "workspace"),
    }


class AgentSpaceOrchestrator:
    """Coordinates subagents, tools, review flow, and observability."""

    def __init__(
        self,
        *,
        settings: SettingsStore,
        logs: LogStore,
        reviews: ReviewStore,
        snapshots: SnapshotStore,
        memory_index: MemoryIndexStore,
        power: PowerManager,
        chat_store: AgentSpaceChatStore,
        team_store: TeamStore,
        skill_store: SkillStore | None,
        browser_manager: Any,
        free_stack_manager: Any | None = None,
    ) -> None:
        self.settings = settings
        self.logs = logs
        self.reviews = reviews
        self.snapshots = snapshots
        self.memory_index = memory_index
        self.power = power
        self.chat_store = chat_store
        self.team_store = team_store
        self.skill_store = skill_store
        self.browser_manager = browser_manager
        self.free_stack_manager = free_stack_manager
        self.runs: dict[str, dict[str, Any]] = {}
        self._run_queues: dict[str, asyncio.Queue] = {}
        self._global_queue: asyncio.Queue = asyncio.Queue()
        self._tasks: dict[str, asyncio.Task] = {}
        self._run_complete_hooks: list[
            Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any] | None] | dict[str, Any] | None]
        ] = []

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = [_run_summary(r) for r in self.runs.values()]
        rows.sort(key=lambda row: row["created_at"], reverse=True)
        return rows[: max(1, limit)]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        run = self.runs.get(run_id)
        if run is None:
            return None
        return dict(run)

    def list_run_messages(
        self,
        run_id: str,
        *,
        limit: int = 200,
        agent_id: str | None = None,
        channel: str | None = None,
    ) -> list[dict[str, Any]]:
        run = self.runs.get(run_id)
        if run is None:
            raise FileNotFoundError(f"Run '{run_id}' not found.")
        rows: list[dict[str, Any]] = list(run.get("messages", []))
        if channel:
            rows = [row for row in rows if str(row.get("channel")) == channel]
        if agent_id:
            rows = [
                row
                for row in rows
                if str(row.get("from")) == agent_id or str(row.get("to")) == agent_id or not str(row.get("to"))
            ]
        rows.sort(key=lambda row: row.get("timestamp", 0))
        return rows[-max(1, limit):]

    async def post_run_message(
        self,
        run_id: str,
        *,
        from_agent: str,
        content: str,
        to_agent: str = "",
        channel: str = "general",
    ) -> dict[str, Any]:
        run = self.runs.get(run_id)
        if run is None:
            raise FileNotFoundError(f"Run '{run_id}' not found.")
        message = await self._send_message(
            run_id=run_id,
            from_agent=from_agent,
            content=content,
            to_agent=to_agent,
            channel=channel,
        )
        return message

    def get_run_queue(self, run_id: str) -> asyncio.Queue:
        queue = self._run_queues.get(run_id)
        if queue is None:
            queue = asyncio.Queue()
            self._run_queues[run_id] = queue
        return queue

    def get_global_queue(self) -> asyncio.Queue:
        return self._global_queue

    def add_run_complete_hook(
        self,
        hook: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any] | None] | dict[str, Any] | None],
    ) -> None:
        self._run_complete_hooks.append(hook)

    async def reset_runtime_state(self) -> dict[str, Any]:
        stopped_tasks = 0
        for run in self.runs.values():
            run["stop_requested"] = True
        tasks = list(self._tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
                stopped_tasks += 1
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.runs.clear()
        self._run_queues.clear()
        self._tasks.clear()
        self._global_queue = asyncio.Queue()
        return {"stopped_tasks": stopped_tasks}

    async def start_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.power.is_enabled():
            raise RuntimeError("Agent Space is OFF. Turn power ON before starting runs.")
        run_id = str(uuid.uuid4())
        now = _now()
        objective = str(payload.get("objective") or "").strip()
        if not objective:
            raise RuntimeError("Run objective is required.")
        auto_added_skills: list[dict[str, Any]] = []
        selected_skills: list[dict[str, Any]] = []
        skill_context = ""
        if self.skill_store is not None:
            try:
                auto_added_skills = await self.skill_store.auto_add_for_objective(objective, limit=3)
                selected_skills = self.skill_store.select_for_objective(objective, limit=8)
                skill_context = self.skill_store.build_context(selected_skills, max_chars=12000)
            except Exception:
                logger.warning("Failed to auto-add/select skills for run objective", exc_info=True)
        allowed_paths = self._normalize_allowed_paths(payload.get("allowed_paths", []))
        _raw_scope = str(payload.get("review_scope") or "workspace").strip().lower()
        review_scope = _raw_scope if _raw_scope in ("workspace", "jimai") else "workspace"
        requested_team_id = str(payload.get("team_id") or "").strip() or None
        requested_team_name = ""
        if isinstance(payload.get("team"), dict):
            requested_team_name = str(payload["team"].get("name") or "").strip()
        if requested_team_id:
            existing_team = self.team_store.get_team(requested_team_id)
            if existing_team is None:
                raise RuntimeError(f"Team '{requested_team_id}' not found.")
            requested_team_name = str(existing_team.get("name", "")).strip()
        run = {
            "id": run_id,
            "objective": objective,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "ended_at": None,
            "events": [],
            "review_ids": [],
            "snapshot_ids": [],
            "action_count": 0,
            "error": None,
            "stop_requested": False,
            "team_id": requested_team_id,
            "team_name": requested_team_name or None,
            "skills": [str(item.get("slug") or item.get("name") or "") for item in selected_skills if str(item.get("slug") or item.get("name") or "").strip()],
            "auto_added_skills": [str(item.get("slug") or item.get("name") or "") for item in auto_added_skills if str(item.get("slug") or item.get("name") or "").strip()],
            "skill_context": skill_context,
            "messages": [],
            "allowed_paths": allowed_paths,
            "completion_summary": None,
            "review_scope": review_scope,
        }
        self.runs[run_id] = run
        self.logs.increment("runs_started", 1)
        await self._emit(
            run_id,
            "run.queued",
            f"Queued run {run_id}",
            {
                "objective": objective,
                "skills": list(run.get("skills") or []),
                "auto_added_skills": list(run.get("auto_added_skills") or []),
            },
        )
        if auto_added_skills:
            await self._emit(
                run_id,
                "run.skills",
                "Auto-generated new reusable skills for this objective.",
                {"created": auto_added_skills},
            )
        task = asyncio.create_task(self._execute_run(run_id, payload))
        self._tasks[run_id] = task
        return _run_summary(run)

    async def request_stop(self, run_id: str) -> dict[str, Any]:
        run = self.runs.get(run_id)
        if run is None:
            raise FileNotFoundError(f"Run '{run_id}' not found.")
        run["stop_requested"] = True
        run["updated_at"] = _now()
        await self._emit(run_id, "run.stop_requested", "Stop requested; run will halt at next step.", {})
        return _run_summary(run)

    async def _emit(self, run_id: str, event_type: str, message: str, data: dict[str, Any]) -> None:
        event = {
            "timestamp": _now(),
            "run_id": run_id,
            "type": event_type,
            "message": message,
            "data": data,
        }
        run = self.runs.get(run_id)
        if run is not None:
            run.setdefault("events", []).append(event)
            run["updated_at"] = _now()
        self.logs.log_event(run_id, event)
        await self.get_run_queue(run_id).put(event)
        await self._global_queue.put(event)

    async def _notify_run_complete_hooks(
        self,
        *,
        run: dict[str, Any],
        payload: dict[str, Any],
        completion_summary: dict[str, Any],
    ) -> None:
        if not self._run_complete_hooks:
            return
        for hook in list(self._run_complete_hooks):
            try:
                outcome = hook(run, payload, completion_summary)
                if asyncio.iscoroutine(outcome):
                    outcome = await outcome
                if isinstance(outcome, dict) and outcome:
                    await self._emit(
                        str(run.get("id") or ""),
                        "run.auto_recovery",
                        "Automatic post-run recovery evaluation completed.",
                        outcome,
                    )
            except Exception as exc:
                await self._emit(
                    str(run.get("id") or ""),
                    "run.auto_recovery_error",
                    "Automatic post-run recovery evaluation failed.",
                    {"error": str(exc)},
                )

    async def _send_message(
        self,
        *,
        run_id: str,
        from_agent: str,
        content: str,
        to_agent: str = "",
        channel: str = "general",
    ) -> dict[str, Any]:
        run = self.runs.get(run_id)
        if run is None:
            raise RuntimeError(f"Run '{run_id}' not found.")
        msg = {
            "id": str(uuid.uuid4()),
            "timestamp": _now(),
            "run_id": run_id,
            "from": from_agent,
            "to": to_agent or "",
            "channel": channel or "general",
            "content": content,
            "team_id": run.get("team_id"),
        }
        messages = list(run.get("messages", []))
        messages.append(msg)
        run["messages"] = messages[-4000:]

        team_id = run.get("team_id")
        if team_id:
            try:
                self.team_store.append_message(
                    str(team_id),
                    run_id=run_id,
                    from_agent=from_agent,
                    to_agent=to_agent,
                    channel=channel,
                    content=content,
                )
            except Exception:
                logger.warning("Failed to append message to team store for run %s", run_id, exc_info=True)

        await self._emit(
            run_id,
            "agent.message",
            f"{from_agent} -> {to_agent or 'broadcast'} [{channel or 'general'}]",
            {"message": msg},
        )
        return msg

    def _read_messages(
        self,
        *,
        run_id: str,
        requester: str,
        channel: str = "",
        since: int = 0,
        from_agent: str = "",
        include_private_sent: bool = True,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        run = self.runs.get(run_id)
        if run is None:
            raise RuntimeError(f"Run '{run_id}' not found.")
        rows: list[dict[str, Any]] = list(run.get("messages", []))
        if since > 0:
            rows = rows[since:]
        if channel:
            rows = [row for row in rows if str(row.get("channel")) == channel]
        if from_agent:
            rows = [row for row in rows if str(row.get("from")) == from_agent]

        visible: list[dict[str, Any]] = []
        for row in rows:
            to_agent = str(row.get("to") or "")
            sender = str(row.get("from") or "")
            if not to_agent:
                visible.append(row)
                continue
            if to_agent == requester:
                visible.append(row)
                continue
            if include_private_sent and sender == requester:
                visible.append(row)
        visible.sort(key=lambda row: row.get("timestamp", 0))
        return visible[-max(1, limit):]

    @staticmethod
    def _sanitize_role(role: str) -> str:
        return orch_helpers._sanitize_role(role)

    def _assess_complexity(
        self,
        *,
        objective: str,
        subagent_count: int,
        required_check_count: int,
    ) -> dict[str, Any]:
        text = objective.lower()
        score = 0
        signals: list[str] = []

        if len(text) > 280:
            score += 1
            signals.append("long_objective")
        if len(text) > 900:
            score += 2
            signals.append("very_long_objective")

        keyword_groups = [
            ("architecture", ("distributed", "microservice", "orchestr", "multi-tenant", "pipeline")),
            ("security", ("auth", "security", "compliance", "permission", "privacy", "encryption")),
            ("product_surface", ("mobile", "desktop", "browser", "api", "websocket", "realtime")),
            ("ai_scope", ("agent", "llm", "model", "prompt", "workflow", "automation")),
            ("delivery", ("deploy", "docker", "kubernetes", "ci", "cd", "export")),
        ]
        for label, keys in keyword_groups:
            if any(k in text for k in keys):
                score += 1
                signals.append(label)

        if subagent_count >= 5:
            score += 1
            signals.append("team_5_plus")
        if subagent_count >= 8:
            score += 1
            signals.append("team_8_plus")
        if required_check_count >= 2:
            score += 1
            signals.append("checks_2_plus")
        if required_check_count >= 5:
            score += 1
            signals.append("checks_5_plus")

        if score <= 2:
            level = "low"
        elif score <= 5:
            level = "medium"
        else:
            level = "high"

        return {"level": level, "score": score, "signals": signals}

    def _default_subagent_team(
        self,
        *,
        payload_actions: Any,
        required_checks: list[str],
    ) -> list[dict[str, Any]]:
        actions = list(payload_actions) if isinstance(payload_actions, list) else []
        return [
            {"id": "planner", "role": "planner", "depends_on": []},
            {"id": "worker", "role": "coder", "depends_on": ["planner"], "actions": actions},
            {"id": "tester", "role": "tester", "depends_on": ["worker"], "checks": list(required_checks)},
            {"id": "verifier", "role": "verifier", "depends_on": ["worker", "tester"]},
        ]

    @staticmethod
    def _with_unique_id(existing: set[str], preferred: str, fallback_prefix: str) -> str:
        return orch_helpers._with_unique_id(existing, preferred, fallback_prefix)

    @staticmethod
    def _dedupe_list(values: list[str]) -> list[str]:
        return orch_helpers._dedupe_list(values)

    def _resolve_agent_model(self, *, spec: dict[str, Any], agent_id: str, role: str) -> str:
        explicit = str(spec.get("model") or "").strip()
        if explicit:
            return explicit
        cfg = self.settings.get()
        default_model = str(cfg.get("model", "qwen2.5-coder:14b"))
        raw_map = cfg.get("agent_models", {})
        if not isinstance(raw_map, dict):
            return default_model

        candidates = [
            agent_id,
            f"id:{agent_id}",
            role,
            f"role:{role}",
            self._sanitize_role(role),
            f"role:{self._sanitize_role(role)}",
        ]
        for key in candidates:
            value = str(raw_map.get(key) or "").strip()
            if value:
                return value
        return default_model

    def _normalize_subagents(
        self,
        *,
        subagents: Any,
        objective: str,
        required_checks: list[str],
        payload_actions: Any,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        raw_agents = list(subagents) if isinstance(subagents, list) else []
        if not raw_agents:
            raw_agents = self._default_subagent_team(
                payload_actions=payload_actions,
                required_checks=required_checks,
            )

        normalized: list[dict[str, Any]] = []
        existing_ids: set[str] = set()
        for idx, row in enumerate(raw_agents):
            if not isinstance(row, dict):
                continue
            preferred_id = str(row.get("id") or "").strip()
            agent_id = self._with_unique_id(existing_ids, preferred_id, f"agent-{idx + 1}")
            role = self._sanitize_role(str(row.get("role", "coder")))
            depends = [str(dep) for dep in list(row.get("depends_on") or []) if str(dep).strip()]
            depends = self._dedupe_list([dep for dep in depends if dep != agent_id])

            actions = row.get("actions")
            checks = row.get("checks")
            worker_level = row.get("worker_level")
            normalized.append(
                {
                    "id": agent_id,
                    "role": role,
                    "depends_on": depends,
                    "actions": list(actions) if isinstance(actions, list) else [],
                    "checks": [str(c) for c in list(checks or []) if str(c).strip()],
                    "description": str(row.get("description") or ""),
                    "worker_level": int(worker_level) if isinstance(worker_level, int) else None,
                    "model": str(row.get("model") or "").strip(),
                }
            )

        if not normalized:
            normalized = self._default_subagent_team(
                payload_actions=payload_actions,
                required_checks=required_checks,
            )

        planner_idx = next((i for i, spec in enumerate(normalized) if spec.get("role") == "planner"), None)
        if planner_idx is None:
            planner_id = self._with_unique_id(existing_ids, "planner", "planner")
            normalized.insert(0, {"id": planner_id, "role": "planner", "depends_on": [], "actions": [], "checks": [], "description": "", "worker_level": 1, "model": ""})
        else:
            planner_id = str(normalized[planner_idx]["id"])
            normalized[planner_idx]["depends_on"] = []
            if planner_idx != 0:
                planner_spec = normalized.pop(planner_idx)
                normalized.insert(0, planner_spec)

        role_index: dict[str, list[str]] = {}
        for spec in normalized:
            role_key = self._sanitize_role(str(spec.get("role", "coder")))
            role_index.setdefault(role_key, []).append(str(spec.get("id", "")))

        dep_role_aliases = {
            "builder": "coder",
            "architect": "coder",
            "packager": "coder",
            "developer": "coder",
            "engineer": "coder",
            "qa": "tester",
            "security reviewer": "tester",
            "reviewer": "verifier",
            "validator": "verifier",
            "verifier": "verifier",
            "planner": "planner",
            "tester": "tester",
            "coder": "coder",
        }

        def _map_dependency(agent_id: str, dep: str) -> str:
            raw = dep.strip()
            if not raw:
                return ""
            if any(str(spec.get("id", "")) == raw for spec in normalized):
                return raw
            compact_dep = raw.lower().replace("-", " ").replace("_", " ").strip()
            target_role = dep_role_aliases.get(compact_dep)
            if target_role:
                for candidate in role_index.get(target_role, []):
                    if candidate != agent_id:
                        return candidate
            if "engineer" in compact_dep or "developer" in compact_dep or "coder" in compact_dep:
                for candidate in role_index.get("coder", []):
                    if candidate != agent_id:
                        return candidate
            if "test" in compact_dep or compact_dep == "qa":
                for candidate in role_index.get("tester", []):
                    if candidate != agent_id:
                        return candidate
            if "verif" in compact_dep or "validat" in compact_dep:
                for candidate in role_index.get("verifier", []):
                    if candidate != agent_id:
                        return candidate
            if "plan" in compact_dep:
                for candidate in role_index.get("planner", []):
                    if candidate != agent_id:
                        return candidate
            return ""

        for spec in normalized:
            role = str(spec.get("role", "coder"))
            agent_id = str(spec.get("id", "agent"))
            deps_in = [str(dep) for dep in list(spec.get("depends_on") or []) if str(dep).strip() and str(dep) != agent_id]
            deps: list[str] = []
            for dep in deps_in:
                mapped = _map_dependency(agent_id, dep)
                if mapped and mapped != agent_id:
                    deps.append(mapped)
            if role != "planner" and planner_id not in deps:
                deps.insert(0, planner_id)
            spec["depends_on"] = self._dedupe_list(deps)
            if role == "tester" and required_checks and not spec.get("checks"):
                spec["checks"] = list(required_checks)

        verifier_idx = next((i for i, spec in enumerate(normalized) if str(spec.get("role")) == "verifier"), None)
        verification_sources = [
            str(spec.get("id"))
            for spec in normalized
            if str(spec.get("id")) != planner_id and str(spec.get("role")) != "verifier"
        ]
        verification_sources = self._dedupe_list(verification_sources)
        if verifier_idx is None:
            verifier_id = self._with_unique_id(existing_ids, "verifier", "verifier")
            verifier_deps = verification_sources or [planner_id]
            normalized.append(
                {
                    "id": verifier_id,
                    "role": "verifier",
                    "depends_on": verifier_deps,
                    "actions": [],
                    "checks": [],
                    "description": "Cross-check outputs from other workers before completion.",
                    "worker_level": None,
                    "model": "",
                }
            )
        else:
            verifier_spec = normalized[verifier_idx]
            verifier_id = str(verifier_spec.get("id"))
            verifier_spec["depends_on"] = verification_sources or [planner_id]

        complexity = self._assess_complexity(
            objective=objective,
            subagent_count=len(normalized),
            required_check_count=len(required_checks),
        )
        max_level = {"low": 1, "medium": 2, "high": 3}[str(complexity["level"])]

        rank_counter = 0
        for spec in normalized:
            agent_id = str(spec.get("id"))
            role = str(spec.get("role", "coder"))
            if role == "planner":
                level = 1
            elif role == "verifier":
                level = max_level
            else:
                rank_counter += 1
                if max_level == 1:
                    level = 1
                elif max_level == 2:
                    level = 1 if rank_counter <= 2 else 2
                else:
                    level = 1 if rank_counter <= 1 else (2 if rank_counter <= 3 else 3)
            preset_level = spec.get("worker_level")
            if isinstance(preset_level, int):
                level = max(1, min(max_level, preset_level))
            spec["worker_level"] = int(level)
            spec["complexity_level"] = str(complexity["level"])
            spec["model"] = self._resolve_agent_model(
                spec=spec,
                agent_id=agent_id,
                role=role,
            )
            spec["depends_on"] = self._dedupe_list(
                [dep for dep in list(spec.get("depends_on") or []) if dep != agent_id]
            )

        verifier_agents = [
            str(spec.get("id"))
            for spec in normalized
            if str(spec.get("role", "")) == "verifier"
        ]
        return normalized, {
            "planner_agent": planner_id,
            "verifier_agents": verifier_agents,
            "complexity": complexity,
        }

    @staticmethod
    def _worker_scope_line(role: str, worker_level: int, complexity_level: str) -> str:
        return orch_helpers._worker_scope_line(role, worker_level, complexity_level)

    @staticmethod
    def _select_actions_for_worker(
        actions: list[dict[str, Any]],
        *,
        complexity_level: str,
        worker_level: int,
    ) -> list[dict[str, Any]]:
        return orch_helpers._select_actions_for_worker(actions, complexity_level=complexity_level, worker_level=worker_level)

    async def _execute_run(self, run_id: str, payload: dict[str, Any]) -> None:
        run = self.runs[run_id]
        run["status"] = "running"
        run["started_at"] = _now()
        run["updated_at"] = _now()
        from .metrics import record_run_started
        record_run_started()
        settings = self.settings.get()
        review_gate = bool(payload.get("review_gate", settings["review_gate"]))
        allow_shell = bool(payload.get("allow_shell", settings["allow_shell"]))
        command_profile = str(payload.get("command_profile", settings["command_profile"]))
        max_actions = int(payload.get("max_actions", settings["max_actions"]))
        max_seconds = int(payload.get("max_seconds", settings["max_seconds"]))
        required_checks = list(payload.get("required_checks", settings.get("required_checks", [])))
        strict_verification = bool(payload.get("strict_verification", settings.get("strict_verification", False)))
        continue_on_subagent_failure = bool(
            payload.get(
                "continue_on_subagent_failure",
                settings.get("continue_on_subagent_failure", True),
            )
        )
        subagent_retry_attempts = max(0, int(payload.get("subagent_retry_attempts", 2)))
        create_git_checkpoint = bool(
            payload.get("create_git_checkpoint", settings.get("create_git_checkpoint", False))
        )
        autonomous = bool(payload.get("autonomous", True))
        auto_force_research = bool(settings.get("run_auto_force_research_enabled", True))
        if "force_research" in payload:
            force_research = bool(payload.get("force_research"))
        else:
            force_research = bool(
                autonomous
                and auto_force_research
                and self._objective_needs_research(objective=str(payload.get("objective") or ""))
            )
        objective = str(payload["objective"])
        proposed_changes: dict[str, dict[str, Any]] = {}
        direct_changes: dict[str, dict[str, Any]] = {}
        run["messages"] = []
        context: dict[str, Any] = {
            "planned_actions": [],
            "agent_results": {},
            "team_agents": [],
            "team_specs": {},
            "complexity": {},
            "verifier_agents": [],
            "planner_agent": "",
            "skills": list(run.get("skills") or []),
            "skill_context": str(run.get("skill_context") or ""),
            "required_checks": required_checks,
            "force_research": force_research,
            "autonomous": autonomous,
            "explicit_worker_actions": False,
            "self_improve_prompt": str(payload.get("self_improve_prompt") or "").strip(),
            "confirmed_suggestions": [
                str(item).strip()
                for item in list(payload.get("confirmed_suggestions") or [])
                if str(item).strip()
            ],
            "failed_actions": [],
            "recovered_actions": [],
        }
        context["action_retry_attempts"] = max(1, subagent_retry_attempts + 1)
        start_time = _now()

        subagents = payload.get("subagents")
        team_payload = payload.get("team")
        team_id = str(payload.get("team_id") or run.get("team_id") or "").strip()
        team_name = str(run.get("team_name") or "").strip()
        team_agents: list[dict[str, Any]] = []

        if team_id:
            team_data = self.team_store.get_team(team_id)
            if team_data is None:
                raise RuntimeError(f"Team '{team_id}' not found.")
            team_name = str(team_data.get("name", "")).strip()
            team_agents = list(team_data.get("agents", []))
        elif isinstance(team_payload, dict):
            team_name = str(team_payload.get("name") or "Ad-hoc Team").strip()
            team_agents = list(team_payload.get("agents", []))
            if bool(team_payload.get("save", False)):
                saved_team = self.team_store.save_team(
                    team_id=str(team_payload.get("id") or "").strip() or None,
                    name=team_name,
                    description=str(team_payload.get("description") or ""),
                    agents=team_agents,
                    metadata=dict(team_payload.get("metadata") or {}),
                )
                team_id = str(saved_team["id"])

        run["team_id"] = team_id or None
        run["team_name"] = team_name or None

        if (not isinstance(subagents, list) or not subagents) and team_agents:
            subagents = team_agents

        subagents, workflow_meta = self._normalize_subagents(
            subagents=subagents,
            objective=objective,
            required_checks=required_checks,
            payload_actions=payload.get("actions", []),
        )
        context["team_agents"] = [str(s.get("id", f"agent-{i}")) for i, s in enumerate(subagents)]
        context["team_specs"] = {
            str(s.get("id", f"agent-{i}")): dict(s) for i, s in enumerate(subagents)
        }
        context["complexity"] = dict(workflow_meta.get("complexity", {}))
        context["verifier_agents"] = list(workflow_meta.get("verifier_agents", []))
        context["planner_agent"] = str(workflow_meta.get("planner_agent", ""))
        context["explicit_worker_actions"] = any(
            str(spec.get("role", "")) not in {"planner", "verifier"}
            and (
                bool(list(spec.get("actions") or []))
                or bool(list(spec.get("checks") or []))
            )
            for spec in subagents
            if isinstance(spec, dict)
        )

        await self._emit(
            run_id,
            "run.started",
            "Run started.",
            {
                "review_gate": review_gate,
                "command_profile": command_profile,
                "autonomous": autonomous,
                "team_id": run.get("team_id"),
                "team_name": run.get("team_name"),
                "allowed_paths": run.get("allowed_paths", []),
                "complexity": context.get("complexity", {}),
                "planner_agent": context.get("planner_agent", ""),
                "verifier_agents": context.get("verifier_agents", []),
                "skills": list(context.get("skills") or []),
                "strict_verification": strict_verification,
                "continue_on_subagent_failure": continue_on_subagent_failure,
            },
        )
        await self._emit(
            run_id,
            "run.workflow",
            "Workflow normalized with planner-first and verification gates.",
            {
                "subagents": [
                    {
                        "id": str(spec.get("id")),
                        "role": str(spec.get("role", "coder")),
                        "model": str(spec.get("model", "")),
                        "worker_level": int(spec.get("worker_level") or 1),
                        "depends_on": [str(dep) for dep in list(spec.get("depends_on") or []) if str(dep).strip()],
                    }
                    for spec in subagents
                ],
            },
        )

        pending = {str(s.get("id", f"agent-{i}")): dict(s) for i, s in enumerate(subagents)}
        completed: set[str] = set()
        retry_counts: dict[str, int] = {}
        force_recovery_used = False
        failed = False
        error_message = ""
        stopped = False

        while pending:
            if run.get("stop_requested") or not self.power.is_enabled():
                run["status"] = "stopped"
                await self._emit(run_id, "run.stopped", "Run stopped by user or power control.", {})
                self.logs.increment("runs_stopped", 1)
                stopped = True
                from .metrics import record_run_ended
                record_run_ended("stopped")
                break
            if (_now() - start_time) > max_seconds:
                failed = True
                error_message = f"Run exceeded max_seconds={max_seconds}."
                break

            ready_ids = [
                agent_id
                for agent_id, spec in pending.items()
                if all(dep in completed for dep in spec.get("depends_on", []))
            ]
            if not ready_ids:
                pending_ids = set(pending.keys())
                blocked_map: dict[str, list[str]] = {}
                recovered_unknown: dict[str, list[str]] = {}
                for blocked_id, blocked_spec in pending.items():
                    deps = [str(dep) for dep in list(blocked_spec.get("depends_on") or []) if str(dep).strip()]
                    missing = [dep for dep in deps if dep not in completed]
                    blocked_map[blocked_id] = missing
                    unknown = [dep for dep in missing if dep not in pending_ids and dep not in completed]
                    if unknown:
                        recovered_unknown[blocked_id] = unknown
                        blocked_spec["depends_on"] = [dep for dep in deps if dep not in unknown]

                if recovered_unknown:
                    await self._emit(
                        run_id,
                        "run.recover",
                        "Recovered invalid dependencies and continued.",
                        {"recovered_unknown_dependencies": recovered_unknown},
                    )
                    ready_ids = [
                        agent_id
                        for agent_id, spec in pending.items()
                        if all(dep in completed for dep in spec.get("depends_on", []))
                    ]

                if not ready_ids and not force_recovery_used:
                    candidates = [
                        (
                            agent_id,
                            int(spec.get("worker_level") or 1),
                        )
                        for agent_id, spec in pending.items()
                        if str(spec.get("role", "")) != "verifier"
                    ]
                    if candidates:
                        candidates.sort(key=lambda row: row[1])
                        forced_agent = candidates[0][0]
                        forced_spec = pending.get(forced_agent, {})
                        forced_spec["depends_on"] = []
                        force_recovery_used = True
                        ready_ids = [forced_agent]
                        await self._emit(
                            run_id,
                            "run.recover",
                            "Forced progress on one worker to break dependency deadlock.",
                            {"forced_agent": forced_agent},
                        )

                if not ready_ids:
                    failed = True
                    error_message = f"Dependency deadlock detected. blocked={json.dumps(blocked_map, ensure_ascii=False)}"
                    await self._emit(
                        run_id,
                        "run.deadlock",
                        "Run could not recover from dependency deadlock.",
                        {"blocked": blocked_map},
                    )
                    break

            await self._emit(
                run_id,
                "run.batch",
                f"Running subagent batch: {', '.join(ready_ids)}",
                {"ready_ids": ready_ids},
            )
            batch_tasks = [
                self._execute_subagent(
                    run_id=run_id,
                    agent_id=agent_id,
                    spec=pending[agent_id],
                    objective=objective,
                    context=context,
                    review_gate=review_gate,
                    command_profile=command_profile,
                    allow_shell=allow_shell,
                    max_actions=max_actions,
                    proposed_changes=proposed_changes,
                    direct_changes=direct_changes,
                    autonomous=autonomous,
                    action_retry_attempts=int(context.get("action_retry_attempts", 2)),
                )
                for agent_id in ready_ids
            ]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            for idx, result in enumerate(batch_results):
                agent_id = ready_ids[idx]
                agent_spec = dict(pending.get(agent_id) or {})
                agent_role = str(agent_spec.get("role", "coder"))
                if isinstance(result, Exception):
                    attempts = int(retry_counts.get(agent_id, 0))
                    if attempts < subagent_retry_attempts:
                        retry_counts[agent_id] = attempts + 1
                        await self._emit(
                            run_id,
                            "subagent.retry",
                            f"Retrying subagent {agent_id} after transient failure.",
                            {"attempt": attempts + 1, "error": str(result)},
                        )
                        try:
                            result = await self._execute_subagent(
                                run_id=run_id,
                                agent_id=agent_id,
                                spec=pending[agent_id],
                                objective=objective,
                                context=context,
                                review_gate=review_gate,
                                command_profile=command_profile,
                                allow_shell=allow_shell,
                                max_actions=max_actions,
                                proposed_changes=proposed_changes,
                                direct_changes=direct_changes,
                                autonomous=autonomous,
                                action_retry_attempts=int(context.get("action_retry_attempts", 2)),
                            )
                        except Exception as retry_exc:
                            result = retry_exc
                    if isinstance(result, Exception):
                        await self._emit(
                            run_id,
                            "subagent.error",
                            f"Subagent {agent_id} failed.",
                            {"error": str(result)},
                        )
                        failure_record = {
                            "agent_id": agent_id,
                            "role": agent_role,
                            "error": str(result),
                        }
                        context.setdefault("failed_actions", []).append(failure_record)
                        if agent_role == "planner":
                            recovered_plan = self._planner_recovery_result(
                                objective=objective,
                                autonomous=autonomous,
                                force_research=bool(context.get("force_research", False)),
                            )
                            planned_actions = list(recovered_plan.get("actions", []))
                            complexity_for_levels = str(context.get("complexity", {}).get("level", "low"))
                            context["planned_actions"] = planned_actions
                            context["planned_actions_by_level"] = {
                                "1": self._select_actions_for_worker(
                                    planned_actions,
                                    complexity_level=complexity_for_levels,
                                    worker_level=1,
                                ),
                                "2": self._select_actions_for_worker(
                                    planned_actions,
                                    complexity_level=complexity_for_levels,
                                    worker_level=2,
                                ),
                                "3": self._select_actions_for_worker(
                                    planned_actions,
                                    complexity_level=complexity_for_levels,
                                    worker_level=3,
                                ),
                            }
                            context.setdefault("recovered_actions", []).append(
                                {
                                    "agent_id": agent_id,
                                    "method": "planner_recovery",
                                    "planned_action_count": len(planned_actions),
                                }
                            )
                            await self._emit(
                                run_id,
                                "planner.recovered",
                                "Planner failed; deterministic fallback plan generated and run continued.",
                                {
                                    "agent_id": agent_id,
                                    "error": str(result),
                                    "planned_action_count": len(planned_actions),
                                },
                            )
                            result = recovered_plan
                        elif agent_role == "verifier" and not strict_verification:
                            await self._emit(
                                run_id,
                                "verification.skipped",
                                "Verifier errored but strict verification is OFF; continuing run.",
                                {"agent_id": agent_id, "error": str(result)},
                            )
                            result = {
                                "accepted": False,
                                "status": "error",
                                "summary": str(result),
                                "error": str(result),
                                "continued": True,
                            }
                        elif continue_on_subagent_failure and agent_role != "planner":
                            await self._emit(
                                run_id,
                                "subagent.continued",
                                f"Continuing run after {agent_id} failure.",
                                {"agent_id": agent_id, "role": agent_role, "error": str(result)},
                            )
                            result = {
                                "success": False,
                                "error": str(result),
                                "continued": True,
                            }
                        else:
                            failed = True
                            error_message = f"{agent_id} failed: {result}"
                            break
                if isinstance(result, dict) and result.get("stopped"):
                    run["status"] = "stopped"
                    await self._emit(run_id, "run.stopped", "Run stopped by user or power control.", {})
                    self.logs.increment("runs_stopped", 1)
                    stopped = True
                    from .metrics import record_run_ended
                    record_run_ended("stopped")
                    break
                if agent_role == "verifier" and isinstance(result, dict) and not bool(result.get("accepted", True)):
                    await self._emit(
                        run_id,
                        "verification.failed",
                        "Verifier reported failed validation.",
                        {"agent_id": agent_id, "result": result, "strict_verification": strict_verification},
                    )
                    if strict_verification:
                        failed = True
                        error_message = str(
                            result.get("error")
                            or result.get("summary")
                            or "Verification failed."
                        )
                        break
                completed.add(agent_id)
                context["agent_results"][agent_id] = result
                summary = self._summarize_result_for_message(result)
                dependent_targets = [
                    pending_id
                    for pending_id, pending_spec in pending.items()
                    if agent_id in list(pending_spec.get("depends_on", [])) and pending_id != agent_id
                ]
                if dependent_targets:
                    for target in dependent_targets:
                        await self._send_message(
                            run_id=run_id,
                            from_agent=agent_id,
                            to_agent=target,
                            channel="handoff",
                            content=summary,
                        )
                else:
                    await self._send_message(
                        run_id=run_id,
                        from_agent=agent_id,
                        channel="status",
                        content=summary,
                    )
                for verifier_id in list(context.get("verifier_agents", [])):
                    if verifier_id == agent_id:
                        continue
                    await self._send_message(
                        run_id=run_id,
                        from_agent=agent_id,
                        to_agent=verifier_id,
                        channel="verification",
                        content=summary,
                    )
                pending.pop(agent_id, None)
            if failed or stopped:
                break

        if run["status"] == "running" and not failed and not stopped and autonomous:
            if not proposed_changes and not direct_changes:
                fallback_actions = self._fallback_autonomous_actions(objective)
                if fallback_actions:
                    await self._emit(
                        run_id,
                        "run.fallback_actions",
                        "Applying deterministic fallback actions.",
                        {"count": len(fallback_actions)},
                    )
                    for action in fallback_actions:
                        result = await self._execute_action(
                            run_id=run_id,
                            agent_id="fallback-coder",
                            action=action,
                            review_gate=review_gate,
                            command_profile=command_profile,
                            allow_shell=allow_shell,
                            max_actions=max_actions,
                            proposed_changes=proposed_changes,
                            direct_changes=direct_changes,
                            context=context,
                        )
                        if not result.get("success"):
                            failed = True
                            error_message = f"Fallback action failed: {result.get('error', 'unknown error')}"
                            break

        if run["status"] == "running" and not failed and not stopped and autonomous:
            self_learning_enabled = bool(settings.get("self_learning_enabled", True))
            force_self_learning = bool(payload.get("force_self_learning", False))
            deterministic_objective = self._is_deterministic_file_objective(objective)
            should_run_self_learning = self_learning_enabled and (
                force_self_learning or not deterministic_objective
            )
            if should_run_self_learning:
                focus = str(settings.get("self_learning_focus", "general"))
                self_improve_model = self._resolve_agent_model(
                    spec={"model": ""},
                    agent_id="self-improver",
                    role="coder",
                )
                await self._emit(
                    run_id,
                    "self_learning.started",
                    "Autonomous self-learning cycle started.",
                    {"focus": focus, "model": self_improve_model},
                )
                learning_result = await self._execute_action(
                    run_id=run_id,
                    agent_id="self-improver",
                    action={"type": "self_improve", "focus": focus, "model": self_improve_model},
                    review_gate=review_gate,
                    command_profile=command_profile,
                    allow_shell=allow_shell,
                    max_actions=max_actions,
                    proposed_changes=proposed_changes,
                    direct_changes=direct_changes,
                    context=context,
                )
                if learning_result.get("success"):
                    await self._send_message(
                        run_id=run_id,
                        from_agent="self-improver",
                        channel="learning",
                        content=f"Self-learning report prepared (focus={focus}).",
                    )
                    await self._emit(
                        run_id,
                        "self_learning.completed",
                        "Autonomous self-learning cycle completed.",
                        {"focus": focus},
                    )
                else:
                    await self._emit(
                        run_id,
                        "self_learning.failed",
                        "Autonomous self-learning cycle failed; run continued.",
                        {"error": str(learning_result.get("error", "unknown"))},
                    )
            elif self_learning_enabled and deterministic_objective:
                await self._emit(
                    run_id,
                    "self_learning.skipped",
                    "Skipped autonomous self-learning for deterministic objective.",
                    {"reason": "deterministic_objective"},
                )

        if not failed and run["status"] == "running" and required_checks:
            for check_cmd in required_checks:
                await self._emit(run_id, "check.running", f"Running required check: {check_cmd}", {})
                check_result = await self._run_shell(
                    check_cmd,
                    command_profile=command_profile,
                    allow_shell=allow_shell,
                )
                self.logs.log_action(run_id, "tester", {"type": "run_shell", "command": check_cmd}, check_result)
                if not check_result.get("success"):
                    failed = True
                    error_message = f"Required check failed: {check_cmd}"
                    await self._emit(
                        run_id,
                        "check.failed",
                        "A required check failed.",
                        {"command": check_cmd, "result": check_result},
                    )
                    break
                await self._emit(run_id, "check.passed", "Required check passed.", {"command": check_cmd})

        if run["status"] == "running" and not failed and not stopped:
            if proposed_changes:
                review = self.reviews.create_review(
                    run_id=run_id,
                    objective=objective,
                    changes=list(proposed_changes.values()),
                    metadata={
                        "subagents": list(completed),
                        "review_scope": str(run.get("review_scope") or "workspace"),
                    },
                )
                run["review_ids"].append(review["id"])
                self.logs.increment("reviews_created", 1)
                await self._emit(
                    run_id,
                    "review.created",
                    "Proposed changes stored for review.",
                    {"review_id": review["id"], "change_count": len(proposed_changes)},
                )
            if direct_changes:
                snapshot = self.snapshots.create_snapshot(
                    run_id=run_id,
                    note=f"Pre-change snapshot for direct-apply run {run_id}",
                    files=list(direct_changes.values()),
                    create_git_checkpoint=create_git_checkpoint,
                )
                run["snapshot_ids"].append(snapshot["id"])
                await self._emit(
                    run_id,
                    "snapshot.created",
                    "Snapshot created for direct changes.",
                    {"snapshot_id": snapshot["id"]},
                )

        from .metrics import record_run_ended, record_run_error
        if failed:
            run["status"] = "failed"
            run["error"] = error_message
            self.logs.increment("runs_failed", 1)
            await self._emit(run_id, "run.failed", "Run failed.", {"error": error_message})
            record_run_ended("failed")
            record_run_error("unknown")
        elif run["status"] == "running":
            run["status"] = "completed"
            self.logs.increment("runs_completed", 1)
            record_run_ended("completed")
            await self._emit(
                run_id,
                "run.completed",
                "Run completed.",
                {
                    "review_ids": run.get("review_ids", []),
                    "snapshot_ids": run.get("snapshot_ids", []),
                },
            )

        completion_summary = self._build_completion_summary(
            run=run,
            context=context,
            proposed_changes=proposed_changes,
            direct_changes=direct_changes,
        )
        run["completion_summary"] = completion_summary
        await self._emit(
            run_id,
            "run.summary",
            "Run summary generated.",
            {"summary": completion_summary},
        )
        await self._notify_run_complete_hooks(
            run=run,
            payload=payload,
            completion_summary=completion_summary,
        )
        await self._maybe_send_phone_notification(run=run, completion_summary=completion_summary)

        run["ended_at"] = _now()
        run["updated_at"] = _now()
        self.memory_index.add_run_memory(
            {
                "run_id": run_id,
                "objective": objective,
                "status": run["status"],
                "created_at": run["created_at"],
                "ended_at": run["ended_at"],
                "review_ids": run.get("review_ids", []),
                "snapshot_ids": run.get("snapshot_ids", []),
                "completion_summary": completion_summary,
            }
        )
        self._tasks.pop(run_id, None)

    async def _maybe_send_phone_notification(
        self,
        *,
        run: dict[str, Any],
        completion_summary: dict[str, Any],
    ) -> None:
        cfg = self.settings.get()
        if not bool(cfg.get("phone_notifications_enabled", False)):
            return
        if self.free_stack_manager is None:
            return

        status = str(run.get("status", "")).strip().lower()
        notify_on_failure = bool(cfg.get("phone_notifications_on_failure", True))
        if status != "completed" and not notify_on_failure:
            return

        started_at = float(run.get("started_at") or run.get("created_at") or _now())
        duration_seconds = max(0, int(_now() - started_at))
        min_seconds = max(0, int(cfg.get("phone_notification_min_seconds", 120)))
        if status == "completed" and duration_seconds < min_seconds:
            return

        summary_text = str(completion_summary.get("text") or "").strip()
        objective = str(run.get("objective") or "").strip()
        title = f"jimAI Run {status.title()}"
        body = (
            f"Run {run.get('id', '')[:8]} • {status} • {duration_seconds}s\n"
            f"{objective[:200]}\n"
            f"{summary_text[:600]}"
        ).strip()

        result = await self.free_stack_manager.send_phone_notification(
            title=title,
            message=body,
            priority=8 if status != "completed" else 5,
        )
        if result.get("ok"):
            await self._emit(
                str(run.get("id") or ""),
                "notification.sent",
                "Phone notification sent.",
                {"provider": str(result.get("provider") or "gotify")},
            )
            return
        if result.get("skipped"):
            await self._emit(
                str(run.get("id") or ""),
                "notification.skipped",
                "Phone notification skipped.",
                {"reason": str(result.get("error") or "disabled")},
            )
            return
        await self._emit(
            str(run.get("id") or ""),
            "notification.failed",
            "Phone notification failed.",
            {"error": str(result.get("error") or "unknown")},
        )

    async def _execute_subagent(
        self,
        *,
        run_id: str,
        agent_id: str,
        spec: dict[str, Any],
        objective: str,
        context: dict[str, Any],
        review_gate: bool,
        command_profile: str,
        allow_shell: bool,
        max_actions: int,
        proposed_changes: dict[str, dict[str, Any]],
        direct_changes: dict[str, dict[str, Any]],
        autonomous: bool,
        action_retry_attempts: int,
    ) -> dict[str, Any]:
        role = str(spec.get("role", "coder"))
        model_for_agent = self._resolve_agent_model(
            spec=spec,
            agent_id=agent_id,
            role=role,
        )
        worker_level = int(spec.get("worker_level") or 1)
        complexity_level = str(
            spec.get("complexity_level")
            or context.get("complexity", {}).get("level", "low")
        )
        scope_line = self._worker_scope_line(role, worker_level, complexity_level)
        await self._emit(
            run_id,
            "subagent.started",
            f"Starting {agent_id} ({role}, L{worker_level}).",
            {"worker_level": worker_level, "complexity": complexity_level, "model": model_for_agent},
        )
        await self._send_message(
            run_id=run_id,
            from_agent="orchestrator",
            to_agent=agent_id,
            channel="control",
            content=f"Start role={role} level=L{worker_level} complexity={complexity_level} model={model_for_agent}. {scope_line}",
        )

        if role == "planner":
            if bool(context.get("explicit_worker_actions", False)) and not autonomous:
                plan_result = {
                    "plan": "Deterministic planner fast-path: explicit team actions already defined.",
                    "actions": [],
                    "research_actions_count": 0,
                    "fast_path": True,
                }
            else:
                plan_result = await self._run_planner(
                    objective,
                    autonomous=autonomous,
                    team_agents=list(context.get("team_agents", [])),
                    model=model_for_agent,
                    web_research_enabled=bool(self.settings.get().get("autonomous_web_research_enabled", True)),
                    force_research=bool(context.get("force_research", False)),
                    skill_context=str(context.get("skill_context", "")),
                )
            planned_actions = list(plan_result.get("actions", []))
            context["planned_actions"] = planned_actions
            context["planned_actions_by_level"] = {
                "1": self._select_actions_for_worker(
                    planned_actions,
                    complexity_level=complexity_level,
                    worker_level=1,
                ),
                "2": self._select_actions_for_worker(
                    planned_actions,
                    complexity_level=complexity_level,
                    worker_level=2,
                ),
                "3": self._select_actions_for_worker(
                    planned_actions,
                    complexity_level=complexity_level,
                    worker_level=3,
                ),
            }
            await self._emit(
                run_id,
                "subagent.completed",
                f"Planner {agent_id} completed.",
                {
                    "planned_action_count": len(context["planned_actions"]),
                    "research_actions_count": int(plan_result.get("research_actions_count", 0)),
                },
            )
            return plan_result

        if role == "verifier":
            verify_result = await self._run_verifier(
                run_id=run_id,
                agent_id=agent_id,
                objective=objective,
                context=context,
                model=model_for_agent,
            )
            await self._emit(
                run_id,
                "subagent.completed",
                f"Verifier {agent_id} completed.",
                {"accepted": bool(verify_result.get("accepted", True))},
            )
            return verify_result

        if role == "tester":
            checks = list(spec.get("checks", []))
            if not checks:
                checks = list(context.get("required_checks", []))
            results: list[dict[str, Any]] = []
            for cmd in checks:
                action = {"type": "run_shell", "command": cmd, "cwd": "."}
                result = await self._execute_action(
                    run_id=run_id,
                    agent_id=agent_id,
                    action=action,
                    review_gate=review_gate,
                    command_profile=command_profile,
                    allow_shell=allow_shell,
                    max_actions=max_actions,
                    proposed_changes=proposed_changes,
                    direct_changes=direct_changes,
                    context=context,
                )
                results.append(result)
            await self._emit(
                run_id,
                "subagent.completed",
                f"Tester {agent_id} completed.",
                {"checks": len(checks)},
            )
            return {"checks": results}

        actions = list(spec.get("actions", []))
        planned_by_level = context.get("planned_actions_by_level")
        if not actions and isinstance(planned_by_level, dict):
            actions = list(planned_by_level.get(str(worker_level), []))
        if not actions and context.get("planned_actions"):
            actions = self._select_actions_for_worker(
                list(context["planned_actions"]),
                complexity_level=complexity_level,
                worker_level=worker_level,
            )
        if not actions and autonomous:
            actions = self._fallback_autonomous_actions(objective)

        action_results: list[dict[str, Any]] = []
        failed_actions: list[dict[str, Any]] = []
        for action in actions:
            if not isinstance(action, dict):
                failure = {
                    "success": False,
                    "error": "Invalid action payload (expected object).",
                    "action": str(action)[:240],
                }
                action_results.append(failure)
                failed_actions.append(failure)
                raise RuntimeError("Subagent received invalid action payload.")

            run = self.runs[run_id]
            if run.get("stop_requested") or not self.power.is_enabled():
                action_results.append({"success": False, "stopped": True, "error": "Run stopped by user or power control."})
                break

            action_type = str(action.get("type", "")).strip()
            result: dict[str, Any] = {"success": False, "error": "Action not executed."}
            resolved = False

            for attempt in range(1, max(1, int(action_retry_attempts)) + 1):
                result = await self._execute_action(
                    run_id=run_id,
                    agent_id=agent_id,
                    action=action,
                    review_gate=review_gate,
                    command_profile=command_profile,
                    allow_shell=allow_shell,
                    max_actions=max_actions,
                    proposed_changes=proposed_changes,
                    direct_changes=direct_changes,
                    context=context,
                )
                action_results.append(result)
                if result.get("stopped"):
                    break
                if result.get("success"):
                    resolved = True
                    if attempt > 1:
                        await self._emit(
                            run_id,
                            "action.retry_success",
                            f"{agent_id} recovered {action_type} after retry.",
                            {"action": action, "attempt": attempt},
                        )
                        context.setdefault("recovered_actions", []).append(
                            {"agent_id": agent_id, "action_type": action_type, "method": "retry", "attempt": attempt}
                        )
                    break
                if attempt < max(1, int(action_retry_attempts)):
                    await self._emit(
                        run_id,
                        "action.retry",
                        f"Retrying {action_type} for {agent_id}.",
                        {
                            "action": action,
                            "attempt": attempt + 1,
                            "error": str(result.get("error") or result.get("stderr") or ""),
                        },
                    )

            if result.get("stopped"):
                break

            if not resolved:
                fallback_actions = self._fallback_actions_for_failed_action(
                    action=action,
                    objective=objective,
                    error=str(result.get("error") or result.get("stderr") or ""),
                )
                if self._is_recoverable_action_type(action_type) and fallback_actions:
                    for fallback_idx, fallback_action in enumerate(fallback_actions, start=1):
                        await self._emit(
                            run_id,
                            "action.fallback",
                            f"{agent_id} trying fallback {fallback_idx} for {action_type}.",
                            {"original_action": action, "fallback_action": fallback_action},
                        )
                        fallback_result = await self._execute_action(
                            run_id=run_id,
                            agent_id=agent_id,
                            action=fallback_action,
                            review_gate=review_gate,
                            command_profile=command_profile,
                            allow_shell=allow_shell,
                            max_actions=max_actions,
                            proposed_changes=proposed_changes,
                            direct_changes=direct_changes,
                            context=context,
                        )
                        action_results.append(fallback_result)
                        if fallback_result.get("success"):
                            resolved = True
                            await self._emit(
                                run_id,
                                "action.fallback_success",
                                f"{agent_id} recovered {action_type} using fallback.",
                                {"original_action": action, "fallback_action": fallback_action},
                            )
                            context.setdefault("recovered_actions", []).append(
                                {"agent_id": agent_id, "action_type": action_type, "method": "fallback", "fallback_index": fallback_idx}
                            )
                            break
                        if fallback_result.get("stopped"):
                            result = fallback_result
                            break
                    if result.get("stopped"):
                        break

            if not resolved:
                failure_entry = {
                    "agent_id": agent_id,
                    "action_type": action_type,
                    "action": action,
                    "error": str(result.get("error") or result.get("stderr") or "unknown error"),
                }
                failed_actions.append(failure_entry)
                context.setdefault("failed_actions", []).append(failure_entry)
                raise RuntimeError(
                    f"Action '{action_type}' failed after retries/fallbacks: {failure_entry['error']}"
                )

        await self._emit(
            run_id,
            "subagent.completed",
            f"Subagent {agent_id} completed.",
            {"action_count": len(action_results)},
        )
        return {
            "success": len(failed_actions) == 0,
            "actions": action_results,
            "failed_actions": failed_actions,
            "stopped": any(r.get("stopped") for r in action_results),
        }

    async def _run_planner(
        self,
        objective: str,
        autonomous: bool,
        team_agents: list[str],
        *,
        model: str,
        web_research_enabled: bool,
        force_research: bool = False,
        skill_context: str = "",
    ) -> dict[str, Any]:
        cfg = self.settings.get()
        deep_research_enabled = bool(cfg.get("deep_research_before_build_enabled", True))
        deep_research_min_queries = max(1, int(cfg.get("deep_research_min_queries", 3)))
        effective_web_research_enabled = bool(web_research_enabled or force_research)
        effective_deep_research_enabled = bool(deep_research_enabled or force_research)
        deterministic_file_objective = self._is_deterministic_file_objective(objective)
        research_required = bool(force_research or self._objective_needs_research(objective))
        planner_model_timeout_seconds = max(5, int(cfg.get("planner_model_timeout_seconds", 45)))

        fallback_actions = self._fallback_autonomous_actions(objective) if autonomous else []
        research_actions: list[dict[str, Any]] = []
        if (
            autonomous
            and effective_web_research_enabled
            and effective_deep_research_enabled
            and research_required
            and not deterministic_file_objective
        ):
            research_actions = self._build_pre_research_actions(
                objective,
                min_queries=deep_research_min_queries,
            )
            fallback_actions = [*research_actions, *fallback_actions]
        elif (
            autonomous
            and effective_web_research_enabled
            and research_required
            and not deterministic_file_objective
        ):
            if not any(str(a.get("type")) in {"web_search", "web_fetch", "browser_open"} for a in fallback_actions if isinstance(a, dict)):
                fallback_actions = [
                    {
                        "type": "web_search",
                        "query": self._research_query_from_objective(objective),
                        "limit": 6,
                    },
                    *fallback_actions,
                ]
        if deterministic_file_objective:
            return {
                "plan": "Deterministic objective fast-path.",
                "actions": [a for a in fallback_actions if isinstance(a, dict)],
                "research_actions_count": len(research_actions),
            }
        team_line = ", ".join(team_agents) if team_agents else "planner,coder,tester"
        skill_block = str(skill_context or "").strip()
        if skill_block:
            skill_block = (
                "Reusable SKILL directives selected for this objective:\n"
                f"{skill_block[:12000]}\n\n"
                "Apply relevant directives while generating plan/actions."
            )
        else:
            skill_block = "No reusable skill directives were selected for this objective."
        research_line = (
            "Web and browser research is enabled and required for this objective. Perform research first "
            "using web_search/web_fetch/browser_* actions before coding actions."
            if research_required and effective_web_research_enabled and effective_deep_research_enabled
            else "Web research is enabled and likely useful for this objective; include at least one research step."
            if research_required and effective_web_research_enabled
            else "Use adaptive policy: skip web research unless uncertainty, freshness, pricing, market, or competitor facts are needed."
        )
        prompt = (
            "You are a coding run planner. Return strict JSON with keys 'plan' and 'actions'. "
            "Allowed action types: read_file, write_file, replace_in_file, run_shell, "
            "index_search, web_search, web_fetch, export, send_message, read_messages, "
            "browser_open, browser_navigate, browser_click, browser_type, browser_extract, browser_screenshot, "
            "browser_cursor_move, browser_cursor_click, browser_cursor_hover, browser_scroll, browser_scroll_page, "
            "browser_scroll_into_view, browser_select, browser_check, browser_press_key, browser_wait_for, "
            "browser_interactive, browser_state, browser_links. "
            "Use send_message/read_messages so subagents can coordinate when helpful. "
            "Prioritize proactive planning, implementation, and self-improving updates when safe. "
            "If no action is needed, return an empty list.\n\n"
            f"{research_line}\n\n"
            f"{skill_block}\n\n"
            f"Team agents: {team_line}\n\n"
            f"Objective:\n{objective}"
        )
        timed_out = False
        try:
            text = await asyncio.wait_for(
                ollama_client.chat_full(
                    model=model,
                    messages=[
                        {"role": "system", "content": "Return valid JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                ),
                timeout=planner_model_timeout_seconds,
            )
            parsed = self._parse_json_object(text)
            if isinstance(parsed, dict):
                actions = parsed.get("actions")
                if not isinstance(actions, list) or (not actions and fallback_actions):
                    actions = fallback_actions
                actions = [a for a in list(actions or []) if isinstance(a, dict)]
                if research_actions and not any(self._is_research_action(a) for a in actions):
                    actions = [*research_actions, *actions]
                if not actions and fallback_actions:
                    actions = [a for a in fallback_actions if isinstance(a, dict)]
                return {
                    "plan": parsed.get("plan", "Autonomous plan"),
                    "actions": actions,
                    "research_actions_count": len(research_actions),
                }
        except asyncio.TimeoutError:
            timed_out = True
        except Exception:
            logger.warning("Unexpected error during autonomous plan generation; using fallback planner", exc_info=True)
        return {
            "plan": (
                "Fallback planner: model timeout, using deterministic autonomous action extraction."
                if timed_out
                else "Fallback planner: use regex-based autonomous action extraction."
            ),
            "actions": fallback_actions,
            "research_actions_count": len(research_actions),
        }

    def _planner_recovery_result(
        self,
        *,
        objective: str,
        autonomous: bool,
        force_research: bool,
    ) -> dict[str, Any]:
        cfg = self.settings.get()
        actions = self._fallback_autonomous_actions(objective) if autonomous else []
        research_actions: list[dict[str, Any]] = []
        web_research_enabled = bool(cfg.get("autonomous_web_research_enabled", True))
        deep_research_enabled = bool(cfg.get("deep_research_before_build_enabled", True))
        deep_research_min_queries = max(1, int(cfg.get("deep_research_min_queries", 3)))
        research_required = bool(force_research or self._objective_needs_research(objective))
        deterministic_file_objective = self._is_deterministic_file_objective(objective)

        if (
            autonomous
            and web_research_enabled
            and research_required
            and not deterministic_file_objective
        ):
            if deep_research_enabled or force_research:
                research_actions = self._build_pre_research_actions(
                    objective,
                    min_queries=deep_research_min_queries,
                )
                actions = [*research_actions, *actions]
            elif not any(
                self._is_research_action(action) for action in actions if isinstance(action, dict)
            ):
                actions = [
                    {
                        "type": "web_search",
                        "query": self._research_query_from_objective(objective),
                        "limit": 6,
                    },
                    *actions,
                ]

        return {
            "plan": "Planner recovery fallback: deterministic autonomous planning.",
            "actions": [row for row in actions if isinstance(row, dict)],
            "research_actions_count": len(research_actions),
            "recovered": True,
        }

    @staticmethod
    def _research_query_from_objective(objective: str) -> str:
        return orch_planning._research_query_from_objective(objective)

    @staticmethod
    def _research_query_variants(objective: str, min_queries: int) -> list[str]:
        return orch_planning._research_query_variants(objective, min_queries)

    @staticmethod
    def _is_research_action(action: dict[str, Any]) -> bool:
        return orch_planning._is_research_action(action)

    def _build_pre_research_actions(self, objective: str, *, min_queries: int) -> list[dict[str, Any]]:
        queries = self._research_query_variants(objective, min_queries=min_queries)
        actions: list[dict[str, Any]] = []
        for query in queries:
            actions.append({"type": "web_search", "query": query, "limit": 8})
            actions.append({"type": "browser_open", "url": f"https://duckduckgo.com/?q={quote_plus(query)}", "headless": True})
            actions.append({"type": "browser_extract", "selector": "body", "max_chars": BROWSER_EXTRACT_MAX_CHARS})
            actions.append({"type": "browser_links", "limit": 15})
        return actions

    @staticmethod
    def _is_deterministic_file_objective(objective: str) -> bool:
        return orch_planning._is_deterministic_file_objective(objective)

    @staticmethod
    def _objective_needs_research(objective: str) -> bool:
        return orch_planning._objective_needs_research(objective)

    @staticmethod
    def _is_recoverable_action_type(action_type: str) -> bool:
        return orch_planning._is_recoverable_action_type(action_type)

    def _fallback_actions_for_failed_action(
        self,
        *,
        action: dict[str, Any],
        objective: str,
        error: str,
    ) -> list[dict[str, Any]]:
        action_type = str(action.get("type", "")).strip()
        fallback: list[dict[str, Any]] = []
        error_text = str(error or "").lower()

        if action_type == "web_fetch":
            url = str(action.get("url", "")).strip()
            if url:
                fallback.append({"type": "web_search", "query": f"{url} official documentation and latest details", "limit": 8})
            fallback.append({"type": "web_search", "query": self._research_query_from_objective(objective), "limit": 8})
            return fallback

        if action_type == "web_search":
            query = str(action.get("query", "")).strip() or self._research_query_from_objective(objective)
            fallback.append({"type": "browser_open", "url": f"https://duckduckgo.com/?q={quote_plus(query)}", "headless": True})
            fallback.append({"type": "browser_extract", "selector": "body", "max_chars": BROWSER_EXTRACT_MAX_CHARS})
            return fallback

        if action_type in {
            "browser_open",
            "browser_navigate",
            "browser_extract",
            "browser_links",
            "browser_state",
            "browser_click",
            "browser_type",
            "browser_screenshot",
            "browser_cursor_move",
            "browser_cursor_click",
            "browser_cursor_hover",
            "browser_scroll",
            "browser_cursor_scroll",
            "browser_scroll_page",
            "browser_scroll_into_view",
            "browser_select",
            "browser_check",
            "browser_press_key",
            "browser_wait_for",
            "browser_interactive",
            "browser_close",
            "browser_close_all",
        }:
            url = str(action.get("url", "")).strip()
            if url:
                fallback.append({"type": "browser_open", "url": url, "headless": True})
            else:
                fallback.append(
                    {
                        "type": "browser_open",
                        "url": f"https://duckduckgo.com/?q={quote_plus(self._research_query_from_objective(objective))}",
                        "headless": True,
                    }
                )
            fallback.append({"type": "browser_extract", "selector": "body", "max_chars": BROWSER_EXTRACT_MAX_CHARS})
            return fallback

        if action_type == "run_shell":
            cmd = str(action.get("command", "")).strip()
            cwd = str(action.get("cwd", ".")).strip() or "."
            if cmd and "timeout" in error_text:
                fallback.append({"type": "run_shell", "command": cmd, "cwd": cwd})
            if cmd:
                fallback.append({"type": "read_file", "path": "README.md"})
            return fallback

        return fallback

    async def _run_verifier(
        self,
        *,
        run_id: str,
        agent_id: str,
        objective: str,
        context: dict[str, Any],
        model: str,
    ) -> dict[str, Any]:
        verification_msgs = self._read_messages(
            run_id=run_id,
            requester=agent_id,
            channel="verification",
            limit=300,
        )
        handoff_msgs = self._read_messages(
            run_id=run_id,
            requester=agent_id,
            channel="handoff",
            limit=200,
        )
        agent_results = dict(context.get("agent_results") or {})
        summarized_results = []
        for key, value in list(agent_results.items())[:20]:
            summarized_results.append(
                {
                    "agent": str(key),
                    "result_summary": self._summarize_result_for_message(value)[:900],
                }
            )

        unresolved_failures = len(list(context.get("failed_actions") or []))
        if unresolved_failures > 0:
            fallback_status = "fail"
            fallback_summary = "Verification fallback: unresolved worker/action failures were detected."
        elif summarized_results:
            fallback_status = "pass"
            fallback_summary = "Verification fallback: reviewed available worker outputs."
        else:
            fallback_status = "needs_revision"
            fallback_summary = "No worker outputs were available for verification."
        report: dict[str, Any] = {
            "status": fallback_status,
            "summary": fallback_summary,
            "followups": [],
            "checked_messages": len(verification_msgs) + len(handoff_msgs),
            "checked_results": len(summarized_results),
        }

        if bool(context.get("explicit_worker_actions", False)) and not bool(context.get("autonomous", True)):
            summary_line = f"{str(report.get('status', 'needs_revision')).upper()}: {str(report.get('summary', '')).strip()}"
            await self._send_message(
                run_id=run_id,
                from_agent=agent_id,
                channel="verification-report",
                content=summary_line[:1600],
            )
            accepted = str(report.get("status")) != "fail"
            return {
                "accepted": accepted,
                "status": str(report.get("status")),
                "summary": str(report.get("summary", "")),
                "followups": list(report.get("followups") or []),
                "checked_messages": int(report.get("checked_messages", 0)),
                "checked_results": int(report.get("checked_results", 0)),
                "error": "" if accepted else str(report.get("summary", "Verification failed")),
            }

        prompt = (
            "You are a strict autonomous run verifier. Return JSON only with keys: "
            "status (pass|needs_revision|fail), summary (string), followups (array of strings).\n\n"
            f"Objective:\n{objective}\n\n"
            f"Applied skills:\n{json.dumps(list(context.get('skills') or []), ensure_ascii=False)}\n\n"
            f"Verification messages:\n{json.dumps(verification_msgs[-40:], ensure_ascii=False)}\n\n"
            f"Handoff messages:\n{json.dumps(handoff_msgs[-30:], ensure_ascii=False)}\n\n"
            f"Worker results:\n{json.dumps(summarized_results, ensure_ascii=False)}\n"
        )
        verifier_model_timeout_seconds = max(
            5,
            int(self.settings.get().get("verifier_model_timeout_seconds", 30)),
        )
        try:
            text = await asyncio.wait_for(
                ollama_client.chat_full(
                    model=model,
                    messages=[
                        {"role": "system", "content": "Return strict JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                ),
                timeout=verifier_model_timeout_seconds,
            )
            parsed = self._parse_json_object(text) or {}
            status = str(parsed.get("status", "")).strip().lower()
            if status not in {"pass", "needs_revision", "fail"}:
                status = fallback_status
            summary = str(parsed.get("summary") or fallback_summary).strip() or fallback_summary
            followups = [
                str(item).strip()
                for item in list(parsed.get("followups") or [])
                if str(item).strip()
            ][:8]
            report.update({"status": status, "summary": summary, "followups": followups})
        except Exception:
            logger.warning("Failed to parse verification report JSON from model response", exc_info=True)

        summary_line = f"{str(report.get('status', 'needs_revision')).upper()}: {str(report.get('summary', '')).strip()}"
        await self._send_message(
            run_id=run_id,
            from_agent=agent_id,
            channel="verification-report",
            content=summary_line[:1600],
        )

        if list(report.get("followups") or []):
            targets = [
                str(worker_id)
                for worker_id in list(context.get("team_agents", []))
                if str(worker_id) not in {"", agent_id, str(context.get("planner_agent", ""))}
            ]
            for target in targets[:8]:
                await self._send_message(
                    run_id=run_id,
                    from_agent=agent_id,
                    to_agent=target,
                    channel="verification",
                    content=f"Follow-up requested: {'; '.join(list(report.get('followups') or [])[:3])}",
                )

        accepted = str(report.get("status")) != "fail"
        return {
            "accepted": accepted,
            "status": str(report.get("status")),
            "summary": str(report.get("summary", "")),
            "followups": list(report.get("followups") or []),
            "checked_messages": int(report.get("checked_messages", 0)),
            "checked_results": int(report.get("checked_results", 0)),
            "error": "" if accepted else str(report.get("summary", "Verification failed")),
        }

    def _parse_json_object(self, text: str) -> dict[str, Any] | None:
        try:
            return json.loads(text)
        except Exception:
            logger.warning("Direct JSON parse failed; attempting regex extraction", exc_info=True)
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except Exception:
            return None

    def _summarize_result_for_message(self, result: Any) -> str:
        try:
            text = json.dumps(result, ensure_ascii=False)
        except Exception:
            text = str(result)
        if len(text) > 1400:
            return text[:1400] + "...(truncated)"
        return text

    @staticmethod
    def _extract_self_improve_paths(changes: dict[str, dict[str, Any]]) -> list[str]:
        return orch_helpers._extract_self_improve_paths(changes)

    def _build_completion_summary(
        self,
        *,
        run: dict[str, Any],
        context: dict[str, Any],
        proposed_changes: dict[str, dict[str, Any]],
        direct_changes: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        confirmed = [str(item).strip() for item in list(context.get("confirmed_suggestions") or []) if str(item).strip()]
        prompt = str(context.get("self_improve_prompt") or "").strip()
        failed_actions = list(context.get("failed_actions") or [])
        recovered_actions = list(context.get("recovered_actions") or [])
        self_paths = self._extract_self_improve_paths(proposed_changes) + self._extract_self_improve_paths(direct_changes)
        dedup_self_paths: list[str] = []
        for path in self_paths:
            if path not in dedup_self_paths:
                dedup_self_paths.append(path)

        text_parts = [
            f"Status: {str(run.get('status', 'unknown'))}.",
            f"Actions executed: {int(run.get('action_count', 0))}.",
            f"Review diffs: {len(list(run.get('review_ids') or []))}.",
            f"Snapshots: {len(list(run.get('snapshot_ids') or []))}.",
        ]
        if prompt:
            text_parts.append(f"Prompt: {prompt[:220]}.")
        if confirmed:
            text_parts.append(f"Confirmed goals: {'; '.join(confirmed[:4])}.")
        if dedup_self_paths:
            text_parts.append(f"Self-improve outputs: {', '.join(dedup_self_paths[:3])}.")
        if recovered_actions:
            text_parts.append(f"Recovered actions: {len(recovered_actions)}.")
        if failed_actions:
            text_parts.append(f"Unresolved action failures: {len(failed_actions)}.")

        summary_text = " ".join(part.strip() for part in text_parts if part.strip()).strip()
        return {
            "text": summary_text,
            "status": str(run.get("status", "")),
            "action_count": int(run.get("action_count", 0)),
            "review_count": len(list(run.get("review_ids") or [])),
            "snapshot_count": len(list(run.get("snapshot_ids") or [])),
            "prompt": prompt,
            "confirmed_suggestions": confirmed,
            "self_improve_paths": dedup_self_paths,
            "recovered_actions": len(recovered_actions),
            "failed_actions": len(failed_actions),
        }

    def _resolve_browser_session(
        self,
        *,
        context: dict[str, Any],
        agent_id: str,
        action: dict[str, Any],
    ) -> str:
        explicit = str(action.get("session_id") or "").strip()
        if explicit:
            return explicit
        by_agent = context.setdefault("agent_browser_sessions", {})
        existing = str(by_agent.get(agent_id) or "").strip()
        if existing:
            return existing
        raise RuntimeError(
            "No browser session available. Call browser_open first or pass session_id."
        )

    async def _build_self_improvement_report(
        self,
        *,
        objective: str,
        focus: str,
        model: str,
    ) -> str:
        metrics = self.logs.get_metrics()
        recent = self.memory_index.list_recent_runs(limit=20)
        failures = [row for row in recent if str(row.get("status")) == "failed"]
        stopped = [row for row in recent if str(row.get("status")) == "stopped"]
        base = [
            "# Agent Space Self-Improvement Report",
            "",
            f"- focus: {focus}",
            f"- generated_at_unix: {int(_now())}",
            "",
            "## Metrics",
            f"- runs_started: {metrics.get('runs_started', 0)}",
            f"- runs_completed: {metrics.get('runs_completed', 0)}",
            f"- runs_failed: {metrics.get('runs_failed', 0)}",
            f"- runs_stopped: {metrics.get('runs_stopped', 0)}",
            f"- actions_total: {metrics.get('actions_total', 0)}",
            f"- actions_failed: {metrics.get('actions_failed', 0)}",
            "",
            "## Heuristic Suggestions",
        ]

        if failures:
            base.append("- Increase required checks for high-risk run types.")
            base.append("- Tighten command profile for autonomous runs that fail on shell actions.")
        else:
            base.append("- Failure rate is low; focus on throughput improvements and batch scheduling.")
        if stopped:
            base.append("- Add smaller action batches to improve graceful stop responsiveness.")
        else:
            base.append("- Keep current stop-loop cadence; no stop bottleneck detected.")
        base.append("- Maintain review gate for self-modifying actions.")
        base.append("")
        base.append("## Recent Runs")
        for row in recent[:10]:
            base.append(
                f"- {row.get('run_id', '')}: status={row.get('status', '')} objective={str(row.get('objective', ''))[:80]}"
            )

        draft = "\n".join(base)

        prompt = (
            "You are an autonomous agent engineer. Improve this report with concrete steps. "
            "Return markdown only.\n\n"
            f"Objective: {objective}\nFocus: {focus}\n\n{draft}"
        )
        try:
            improved = await ollama_client.chat_full(
                model=model,
                messages=[
                    {"role": "system", "content": "Write concise markdown with actionable bullets."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            cleaned = improved.strip()
            if cleaned:
                return cleaned
        except Exception:
            logger.warning("Failed to improve draft answer via model; returning original draft", exc_info=True)
        return draft

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        return orch_helpers._strip_code_fence(text)

    def _extract_repo_paths_from_text(self, text: str) -> list[str]:
        raw = str(text or "")
        candidates: list[str] = []
        for match in re.findall(r"`([^`]+)`", raw):
            value = str(match).strip().replace("\\", "/")
            if value and "/" in value and "." in value:
                candidates.append(value)
        for match in re.findall(r"([A-Za-z0-9_\-./]+?\.[A-Za-z0-9]+)", raw):
            value = str(match).strip().replace("\\", "/")
            if value and "/" in value:
                candidates.append(value)

        deduped: list[str] = []
        for value in candidates:
            try:
                rel, abs_path = self._resolve_repo_path(value)
            except Exception:
                continue
            if not abs_path.exists() or not abs_path.is_file():
                continue
            if rel not in deduped:
                deduped.append(rel)
        return deduped

    def _self_improve_target_paths(
        self,
        *,
        prompt: str,
        confirmed_suggestions: list[str],
    ) -> list[str]:
        paths: list[str] = []
        for text in [prompt, *confirmed_suggestions]:
            for path in self._extract_repo_paths_from_text(text):
                if path not in paths:
                    paths.append(path)
            if len(paths) >= 5:
                return paths[:5]

        prompt_lower = str(prompt or "").lower()
        fallback_candidates: list[str] = []
        if any(token in prompt_lower for token in ("review", "diff", "workflow")):
            fallback_candidates.append("frontend/src/pages/WorkflowReview.tsx")
        if any(token in prompt_lower for token in ("self", "improve", "suggestion")):
            fallback_candidates.append("frontend/src/pages/SelfCode.tsx")
        if any(token in prompt_lower for token in ("setting", "config", "notification")):
            fallback_candidates.append("frontend/src/pages/Settings.tsx")
        fallback_candidates.append("frontend/src/pages/SelfCode.tsx")

        for candidate in fallback_candidates:
            try:
                rel, abs_path = self._resolve_repo_path(candidate)
            except Exception:
                continue
            if abs_path.exists() and abs_path.is_file() and rel not in paths:
                paths.append(rel)
            if len(paths) >= 3:
                break
        return paths[:5]

    async def _rewrite_file_for_self_improve(
        self,
        *,
        rel_path: str,
        current_content: str,
        objective: str,
        prompt: str,
        confirmed_suggestions: list[str],
        focus: str,
        model: str,
    ) -> str | None:
        source = str(current_content or "")
        if not source.strip():
            return None
        if len(source) > 120_000:
            return None

        ask = (
            "You are improving an existing codebase file.\n"
            "Return ONLY the full updated file content (no markdown fences, no commentary).\n"
            "Keep changes minimal and safe. Preserve existing functionality unless directly requested.\n"
            "Do not invent new files. Do not remove core exports.\n\n"
            f"Objective:\n{objective}\n\n"
            f"Self-improve prompt:\n{prompt}\n\n"
            f"Focus:\n{focus}\n\n"
            "Confirmed suggestions:\n"
            + "\n".join(f"- {row}" for row in confirmed_suggestions[:12])
            + "\n\n"
            f"Target file path: {rel_path}\n\n"
            "Current file content:\n"
            f"{source}"
        )
        try:
            text = await ollama_client.chat_full(
                model=model,
                messages=[
                    {"role": "system", "content": "Return full file content only."},
                    {"role": "user", "content": ask},
                ],
                temperature=0.1,
            )
        except Exception:
            return None

        updated = self._strip_code_fence(text)
        if not updated or updated == source:
            return None
        # Guardrail against destructive truncation.
        if len(updated) < max(40, int(len(source) * 0.35)):
            return None
        return updated

    def _fallback_autonomous_actions(self, objective: str) -> list[dict[str, Any]]:
        text = objective.strip()
        if not text:
            return []

        create_match = re.search(
            r"create file\s+([^\s]+)\s+with\s+(.+)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if create_match:
            path = create_match.group(1).strip().strip("'\"")
            content = create_match.group(2).strip().strip("'\"")
            return [{"type": "write_file", "path": path, "content": content}]

        write_match = re.search(
            r"write\s+(.+)\s+to\s+([^\s]+)",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if write_match:
            content = write_match.group(1).strip().strip("'\"")
            path = write_match.group(2).strip().strip("'\"")
            return [{"type": "write_file", "path": path, "content": content}]

        replace_match = re.search(
            r"replace\s+'([^']+)'\s+with\s+'([^']+)'\s+in\s+([^\s]+)",
            text,
            flags=re.IGNORECASE,
        )
        if replace_match:
            return [
                {
                    "type": "replace_in_file",
                    "path": replace_match.group(3),
                    "find": replace_match.group(1),
                    "replace": replace_match.group(2),
                }
            ]

        return []

    @staticmethod
    def _default_self_improve_report_path() -> str:
        return orch_helpers._default_self_improve_report_path()

    async def _execute_action(
        self,
        *,
        run_id: str,
        agent_id: str,
        action: dict[str, Any],
        review_gate: bool,
        command_profile: str,
        allow_shell: bool,
        max_actions: int,
        proposed_changes: dict[str, dict[str, Any]],
        direct_changes: dict[str, dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        run = self.runs[run_id]
        if run["action_count"] >= max_actions:
            raise RuntimeError(f"Action budget exceeded (max_actions={max_actions}).")
        if run.get("stop_requested") or not self.power.is_enabled():
            return {"success": False, "stopped": True, "error": "Run stopped by user or power control."}
        if not isinstance(action, dict):
            return {"success": False, "error": "Action must be an object."}

        run["action_count"] += 1
        action_type = str(action.get("type", "")).strip()
        await self._emit(run_id, "action.started", f"{agent_id} executing {action_type}", {"action": action})

        try:
            if action_type == "read_file":
                rel, abs_path = self._resolve_repo_path(str(action.get("path", "")), run_id=run_id)
                text = self._read_pending_or_disk(rel, abs_path, proposed_changes)
                result = {"success": True, "path": rel, "content": text[:BROWSER_EXTRACT_MAX_CHARS]}
            elif action_type == "write_file":
                rel, abs_path = self._resolve_repo_path(str(action.get("path", "")), run_id=run_id)
                content = str(action.get("content", ""))
                old_text = self._read_pending_or_disk(rel, abs_path, proposed_changes)
                existed_before = abs_path.exists() or rel in proposed_changes
                self._record_change(
                    bucket=proposed_changes if review_gate else direct_changes,
                    rel_path=rel,
                    old_content=old_text,
                    existed_before=existed_before,
                    new_content=content,
                    reason="write_file",
                )
                if not review_gate:
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    abs_path.write_text(content, encoding="utf-8")
                result = {"success": True, "path": rel, "mode": "review" if review_gate else "direct"}
            elif action_type == "replace_in_file":
                rel, abs_path = self._resolve_repo_path(str(action.get("path", "")), run_id=run_id)
                find_text = str(action.get("find", ""))
                replace_text = str(action.get("replace", ""))
                count = int(action.get("count", -1))
                old_text = self._read_pending_or_disk(rel, abs_path, proposed_changes)
                if not find_text:
                    raise RuntimeError("replace_in_file requires non-empty 'find'.")
                if count > 0:
                    new_text = old_text.replace(find_text, replace_text, count)
                else:
                    new_text = old_text.replace(find_text, replace_text)
                if new_text == old_text:
                    raise RuntimeError("replace_in_file made no changes.")
                existed_before = abs_path.exists() or rel in proposed_changes
                self._record_change(
                    bucket=proposed_changes if review_gate else direct_changes,
                    rel_path=rel,
                    old_content=old_text,
                    existed_before=existed_before,
                    new_content=new_text,
                    reason="replace_in_file",
                )
                if not review_gate:
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    abs_path.write_text(new_text, encoding="utf-8")
                result = {"success": True, "path": rel, "mode": "review" if review_gate else "direct"}
            elif action_type == "run_shell":
                cmd = str(action.get("command", ""))
                cwd = str(action.get("cwd", "."))
                result = await self._run_shell(
                    cmd,
                    cwd=cwd,
                    command_profile=command_profile,
                    allow_shell=allow_shell,
                )
            elif action_type == "index_search":
                query = str(action.get("query", ""))
                rows = self.memory_index.search_code_index(query, limit=int(action.get("limit", 20)))
                result = {"success": True, "query": query, "results": rows}
            elif action_type == "web_search":
                query = str(action.get("query", ""))
                result = await search_web(query, limit=int(action.get("limit", 8)))
                result["success"] = bool(result.get("ok"))
            elif action_type == "web_fetch":
                url = str(action.get("url", ""))
                result = await fetch_web(url)
                result["success"] = bool(result.get("ok"))
            elif action_type == "export":
                target = str(action.get("target_folder", "manual_export"))
                include_paths = list(action.get("include_paths", []))
                label = str(action.get("label", ""))
                exported = export_items(target, include_paths, label=label)
                result = {"success": True, **exported}
            elif action_type == "self_improve":
                default_report_path = self._default_self_improve_report_path()
                rel, abs_path = self._resolve_repo_path(
                    str(action.get("path", default_report_path)),
                    run_id=run_id,
                )
                old_text = self._read_pending_or_disk(rel, abs_path, proposed_changes)
                existed_before = abs_path.exists() or rel in proposed_changes
                report = await self._build_self_improvement_report(
                    objective=self.runs[run_id]["objective"],
                    focus=str(action.get("focus", "general")),
                    model=str(action.get("model") or self.settings.get().get("model", "qwen2.5-coder:14b")),
                )
                self._record_change(
                    bucket=proposed_changes if review_gate else direct_changes,
                    rel_path=rel,
                    old_content=old_text,
                    existed_before=existed_before,
                    new_content=report,
                    reason="self_improve",
                )
                if not review_gate:
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    abs_path.write_text(report, encoding="utf-8")
                prompt_text = str(action.get("prompt") or context.get("self_improve_prompt") or "").strip()
                confirmed = [
                    str(item).strip()
                    for item in list(
                        action.get("confirmed_suggestions")
                        or context.get("confirmed_suggestions")
                        or []
                    )
                    if str(item).strip()
                ]
                target_paths = self._self_improve_target_paths(
                    prompt=prompt_text,
                    confirmed_suggestions=confirmed,
                )
                edited_paths: list[str] = []
                for target_path in target_paths:
                    if target_path == rel:
                        continue
                    try:
                        target_rel, target_abs = self._resolve_repo_path(target_path, run_id=run_id)
                    except Exception:
                        continue
                    current = self._read_pending_or_disk(target_rel, target_abs, proposed_changes)
                    updated = await self._rewrite_file_for_self_improve(
                        rel_path=target_rel,
                        current_content=current,
                        objective=self.runs[run_id]["objective"],
                        prompt=prompt_text,
                        confirmed_suggestions=confirmed,
                        focus=str(action.get("focus", "general")),
                        model=str(action.get("model") or self.settings.get().get("model", "qwen2.5-coder:14b")),
                    )
                    if not updated or updated == current:
                        continue
                    existed_target = target_abs.exists() or target_rel in proposed_changes
                    self._record_change(
                        bucket=proposed_changes if review_gate else direct_changes,
                        rel_path=target_rel,
                        old_content=current,
                        existed_before=existed_target,
                        new_content=updated,
                        reason="self_improve_code",
                    )
                    if not review_gate:
                        target_abs.parent.mkdir(parents=True, exist_ok=True)
                        target_abs.write_text(updated, encoding="utf-8")
                    edited_paths.append(target_rel)

                result = {
                    "success": True,
                    "path": rel,
                    "mode": "review" if review_gate else "direct",
                    "target_paths": target_paths,
                    "edited_paths": edited_paths,
                    "edited_count": len(edited_paths),
                }
            elif action_type == "browser_open":
                url = str(action.get("url", "")).strip()
                headless = bool(action.get("headless", True))
                vw = action.get("viewport_width")
                vh = action.get("viewport_height")
                opened = await self.browser_manager.open_session(
                    url=url,
                    headless=headless,
                    viewport_width=int(vw) if vw is not None else None,
                    viewport_height=int(vh) if vh is not None else None,
                    user_agent=str(action.get("user_agent") or "").strip(),
                    locale=str(action.get("locale") or "").strip(),
                    timezone_id=str(action.get("timezone_id") or "").strip(),
                    ignore_https_errors=bool(action.get("ignore_https_errors", False)),
                    slow_mo_ms=int(action.get("slow_mo_ms", 0) or 0),
                )
                if opened.get("success"):
                    context.setdefault("agent_browser_sessions", {})[agent_id] = opened["session_id"]
                result = opened
            elif action_type == "browser_navigate":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                url = str(action.get("url", "")).strip()
                result = await self.browser_manager.navigate(session_id, url)
            elif action_type == "browser_click":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                selector = str(action.get("selector", "")).strip()
                result = await self.browser_manager.click(session_id, selector)
            elif action_type == "browser_type":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                selector = str(action.get("selector", "")).strip()
                text = str(action.get("text", ""))
                press_enter = bool(action.get("press_enter", False))
                clear_first = bool(action.get("clear_first", True))
                result = await self.browser_manager.type_text(
                    session_id,
                    selector=selector,
                    text=text,
                    press_enter=press_enter,
                    clear_first=clear_first,
                )
            elif action_type == "browser_extract":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                selector = str(action.get("selector", "body"))
                max_chars = int(action.get("max_chars", 12000))
                result = await self.browser_manager.extract_text(
                    session_id,
                    selector=selector,
                    max_chars=max_chars,
                )
            elif action_type == "browser_screenshot":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                full_page = bool(action.get("full_page", True))
                result = await self.browser_manager.screenshot(session_id, full_page=full_page)
            elif action_type == "browser_cursor_move":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                x = float(action.get("x", 0))
                y = float(action.get("y", 0))
                steps = int(action.get("steps", 1))
                result = await self.browser_manager.cursor_move(
                    session_id,
                    x=x,
                    y=y,
                    steps=steps,
                )
            elif action_type == "browser_cursor_click":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                x = action.get("x")
                y = action.get("y")
                button = str(action.get("button", "left"))
                click_count = int(action.get("click_count", 1))
                delay_ms = int(action.get("delay_ms", 0))
                result = await self.browser_manager.cursor_click(
                    session_id,
                    x=float(x) if x is not None else None,
                    y=float(y) if y is not None else None,
                    button=button,
                    click_count=click_count,
                    delay_ms=delay_ms,
                )
            elif action_type in {"browser_scroll", "browser_cursor_scroll"}:
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                x = action.get("x")
                y = action.get("y")
                dx = float(action.get("dx", 0.0))
                dy = float(action.get("dy", 600.0))
                result = await self.browser_manager.cursor_scroll(
                    session_id,
                    dx=dx,
                    dy=dy,
                    x=float(x) if x is not None else None,
                    y=float(y) if y is not None else None,
                )
            elif action_type == "browser_scroll_page":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                result = await self.browser_manager.scroll_page(
                    session_id,
                    delta_x=float(action.get("delta_x", 0.0)),
                    delta_y=float(action.get("delta_y", 0.0)),
                    position=str(action.get("position", "")),
                )
            elif action_type == "browser_scroll_into_view":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                selector = str(action.get("selector", "")).strip()
                result = await self.browser_manager.scroll_into_view(session_id, selector=selector)
            elif action_type == "browser_select":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                selector = str(action.get("selector", "")).strip()
                result = await self.browser_manager.select_option(
                    session_id,
                    selector=selector,
                    value=str(action.get("value", "")),
                    label=str(action.get("label", "")),
                )
            elif action_type == "browser_check":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                selector = str(action.get("selector", "")).strip()
                result = await self.browser_manager.set_checked(
                    session_id,
                    selector=selector,
                    checked=bool(action.get("checked", True)),
                )
            elif action_type == "browser_press_key":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                result = await self.browser_manager.press_key(
                    session_id,
                    key=str(action.get("key", "")),
                    selector=str(action.get("selector", "")),
                )
            elif action_type == "browser_wait_for":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                result = await self.browser_manager.wait_for(
                    session_id,
                    selector=str(action.get("selector", "")),
                    state=str(action.get("state", "visible")),
                    timeout_ms=int(action.get("timeout_ms", 30000)),
                )
            elif action_type == "browser_interactive":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                limit = int(action.get("limit", 80))
                result = await self.browser_manager.list_interactive(session_id, limit=limit)
            elif action_type == "browser_cursor_hover":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                x = action.get("x")
                y = action.get("y")
                selector = str(action.get("selector", ""))
                result = await self.browser_manager.cursor_hover(
                    session_id,
                    selector=selector,
                    x=float(x) if x is not None else None,
                    y=float(y) if y is not None else None,
                )
            elif action_type == "browser_state":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                include_links = bool(action.get("include_links", False))
                link_limit = int(action.get("link_limit", 40))
                result = await self.browser_manager.get_state(
                    session_id,
                    include_links=include_links,
                    link_limit=link_limit,
                )
            elif action_type == "browser_links":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                limit = int(action.get("limit", 40))
                result = await self.browser_manager.list_links(
                    session_id,
                    limit=limit,
                )
            elif action_type == "browser_close":
                session_id = self._resolve_browser_session(
                    context=context,
                    agent_id=agent_id,
                    action=action,
                )
                result = await self.browser_manager.close_session(session_id)
                if result.get("success"):
                    context.setdefault("agent_browser_sessions", {}).pop(agent_id, None)
            elif action_type == "browser_close_all":
                result = await self.browser_manager.close_all()
                context.setdefault("agent_browser_sessions", {}).pop(agent_id, None)
            elif action_type in {"send_message", "communicate"}:
                content = str(action.get("content", "")).strip()
                if not content:
                    raise RuntimeError("send_message requires non-empty content.")
                to_agent = str(action.get("to") or action.get("to_agent") or "").strip()
                channel = str(action.get("channel") or "general")
                msg = await self._send_message(
                    run_id=run_id,
                    from_agent=agent_id,
                    to_agent=to_agent,
                    channel=channel,
                    content=content,
                )
                result = {"success": True, "message": msg}
            elif action_type == "read_messages":
                channel = str(action.get("channel") or "")
                since = int(action.get("since", 0) or 0)
                from_agent = str(action.get("from") or action.get("from_agent") or "")
                include_private_sent = bool(action.get("include_private_sent", True))
                limit = int(action.get("limit", 200))
                messages = self._read_messages(
                    run_id=run_id,
                    requester=agent_id,
                    channel=channel,
                    since=since,
                    from_agent=from_agent,
                    include_private_sent=include_private_sent,
                    limit=limit,
                )
                result = {"success": True, "messages": messages, "count": len(messages)}
            else:
                raise RuntimeError(f"Unsupported action type '{action_type}'.")
        except Exception as exc:
            result = {"success": False, "error": str(exc)}

        self.logs.log_action(run_id, agent_id, action, result)
        await self._emit(
            run_id,
            "action.completed",
            f"{agent_id} completed {action_type}",
            {"action": action, "result": result},
        )
        return result

    async def _run_shell(
        self,
        command: str,
        *,
        cwd: str = ".",
        command_profile: str,
        allow_shell: bool,
    ) -> dict[str, Any]:
        base = (PROJECT_ROOT / cwd).resolve() if not Path(cwd).is_absolute() else Path(cwd).resolve()
        if not str(base).startswith(str(PROJECT_ROOT.resolve())):
            return {"success": False, "stderr": "cwd outside repository.", "stdout": "", "exit_code": -1}
        try:
            return await run_command(
                command=command,
                cwd=str(base),
                profile=command_profile,
                repo_root=PROJECT_ROOT,
                allow_shell=allow_shell,
                timeout=120,
            )
        except PolicyError as exc:
            return {"success": False, "stderr": str(exc), "stdout": "", "exit_code": -1}

    def _normalize_allowed_paths(self, raw_paths: Any) -> list[str]:
        if not isinstance(raw_paths, list):
            return []
        normalized: list[str] = []
        for item in raw_paths:
            value = str(item or "").strip()
            if not value:
                continue
            candidate = Path(value)
            if candidate.is_absolute():
                abs_path = candidate.resolve()
            else:
                abs_path = (PROJECT_ROOT / candidate).resolve()
            if not str(abs_path).startswith(str(PROJECT_ROOT.resolve())):
                raise RuntimeError(f"allowed_paths entry '{value}' is outside repository.")
            rel = abs_path.relative_to(PROJECT_ROOT).as_posix().strip("/")
            if rel and rel not in normalized:
                normalized.append(rel)
        return normalized

    @staticmethod
    def _is_path_allowed(rel_path: str, allowed_paths: list[str]) -> bool:
        return orch_helpers._is_path_allowed(rel_path, allowed_paths)

    def _resolve_repo_path(self, path_text: str, run_id: str | None = None) -> tuple[str, Path]:
        if not path_text:
            raise RuntimeError("Action path is required.")
        candidate = Path(path_text)
        if candidate.is_absolute():
            abs_path = candidate.resolve()
        else:
            abs_path = (PROJECT_ROOT / candidate).resolve()
        if not str(abs_path).startswith(str(PROJECT_ROOT.resolve())):
            raise RuntimeError(f"Path '{path_text}' is outside repository.")
        rel = abs_path.relative_to(PROJECT_ROOT).as_posix()
        if run_id:
            run = self.runs.get(run_id) or {}
            allowed_paths = list(run.get("allowed_paths") or [])
            if allowed_paths and not self._is_path_allowed(rel, allowed_paths):
                raise RuntimeError(
                    f"Path '{rel}' is outside allowed_paths scope for this run."
                )
        return rel, abs_path

    def _read_pending_or_disk(
        self,
        rel_path: str,
        abs_path: Path,
        pending_changes: dict[str, dict[str, Any]],
    ) -> str:
        if rel_path in pending_changes:
            return str(pending_changes[rel_path].get("new_content", ""))
        if not abs_path.exists():
            return ""
        return abs_path.read_text(encoding="utf-8", errors="replace")

    def _record_change(
        self,
        *,
        bucket: dict[str, dict[str, Any]],
        rel_path: str,
        old_content: str,
        existed_before: bool,
        new_content: str,
        reason: str,
    ) -> None:
        if rel_path in bucket:
            bucket[rel_path]["new_content"] = new_content
            bucket[rel_path]["reason"] = reason
            return
        bucket[rel_path] = {
            "path": rel_path,
            "old_content": old_content,
            "new_content": new_content,
            "existed_before": existed_before,
            "reason": reason,
        }
