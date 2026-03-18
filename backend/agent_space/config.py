"""Agent Space runtime configuration and persisted settings."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from threading import Lock
from typing import Any

from .paths import DATA_ROOT, ensure_layout

SETTINGS_FILE = DATA_ROOT / "settings.json"


DEFAULT_SETTINGS: dict[str, Any] = {
    "model": os.getenv("AGENT_SPACE_MODEL", "qwen2.5-coder:14b"),
    "command_profile": os.getenv("AGENT_SPACE_COMMAND_PROFILE", "safe"),
    "review_gate": os.getenv("AGENT_SPACE_REVIEW_GATE", "true").lower() in ("1", "true", "yes"),
    "allow_shell": os.getenv("AGENT_SPACE_ALLOW_SHELL", "true").lower() in ("1", "true", "yes"),
    "max_actions": int(os.getenv("AGENT_SPACE_MAX_ACTIONS", "40")),
    "max_seconds": int(os.getenv("AGENT_SPACE_MAX_SECONDS", "1200")),
    "subagent_retry_attempts": int(os.getenv("AGENT_SPACE_SUBAGENT_RETRY_ATTEMPTS", "2")),
    "continue_on_subagent_failure": os.getenv("AGENT_SPACE_CONTINUE_ON_SUBAGENT_FAILURE", "true").lower() in ("1", "true", "yes"),
    "required_checks": [],
    "release_gpu_on_off": os.getenv("AGENT_SPACE_RELEASE_GPU", "false").lower() in ("1", "true", "yes"),
    "backend_port": int(os.getenv("BACKEND_PORT", "8000")),
    "frontend_port": int(os.getenv("FRONTEND_PORT", "5173")),
    "desktop_mode": os.getenv("AGENT_SPACE_DESKTOP_MODE", "false").lower() in ("1", "true", "yes"),
    "create_git_checkpoint": os.getenv("AGENT_SPACE_GIT_CHECKPOINT", "false").lower() in ("1", "true", "yes"),
    "run_budget_tokens": int(os.getenv("AGENT_SPACE_RUN_BUDGET_TOKENS", "16000")),
    "proactive_enabled": os.getenv("AGENT_SPACE_PROACTIVE_ENABLED", "false").lower() in ("1", "true", "yes"),
    "proactive_tick_seconds": int(os.getenv("AGENT_SPACE_PROACTIVE_TICK_SECONDS", "5")),
    "phone_notifications_enabled": os.getenv("AGENT_SPACE_PHONE_NOTIFICATIONS_ENABLED", "false").lower() in ("1", "true", "yes"),
    "phone_notification_min_seconds": int(os.getenv("AGENT_SPACE_PHONE_NOTIFICATION_MIN_SECONDS", "120")),
    "phone_notifications_on_failure": os.getenv("AGENT_SPACE_PHONE_NOTIFICATIONS_ON_FAILURE", "true").lower() in ("1", "true", "yes"),
    "auto_self_improve_on_failure_enabled": os.getenv("AGENT_SPACE_AUTO_SELF_IMPROVE_ON_FAILURE_ENABLED", "true").lower() in ("1", "true", "yes"),
    "auto_self_improve_on_failure_include_stopped": os.getenv("AGENT_SPACE_AUTO_SELF_IMPROVE_ON_FAILURE_INCLUDE_STOPPED", "false").lower() in ("1", "true", "yes"),
    "auto_self_improve_on_failure_cooldown_seconds": int(os.getenv("AGENT_SPACE_AUTO_SELF_IMPROVE_ON_FAILURE_COOLDOWN_SECONDS", "180")),
    "auto_self_improve_on_failure_max_per_day": int(os.getenv("AGENT_SPACE_AUTO_SELF_IMPROVE_ON_FAILURE_MAX_PER_DAY", "12")),
    "self_learning_enabled": os.getenv("AGENT_SPACE_SELF_LEARNING_ENABLED", "true").lower() in ("1", "true", "yes"),
    "self_learning_focus": os.getenv("AGENT_SPACE_SELF_LEARNING_FOCUS", "general"),
    "autonomous_web_research_enabled": os.getenv("AGENT_SPACE_WEB_RESEARCH_ENABLED", "true").lower() in ("1", "true", "yes"),
    "chat_auto_web_research_enabled": os.getenv("AGENT_SPACE_CHAT_AUTO_WEB_RESEARCH_ENABLED", "true").lower() in ("1", "true", "yes"),
    "run_auto_force_research_enabled": os.getenv("AGENT_SPACE_RUN_AUTO_FORCE_RESEARCH_ENABLED", "true").lower() in ("1", "true", "yes"),
    "deep_research_before_build_enabled": os.getenv("AGENT_SPACE_DEEP_RESEARCH_ENABLED", "true").lower() in ("1", "true", "yes"),
    "deep_research_min_queries": int(os.getenv("AGENT_SPACE_DEEP_RESEARCH_MIN_QUERIES", "3")),
    "overnight_autonomy_enabled": os.getenv("AGENT_SPACE_OVERNIGHT_AUTONOMY_ENABLED", "true").lower() in ("1", "true", "yes"),
    "overnight_max_hours": int(os.getenv("AGENT_SPACE_OVERNIGHT_MAX_HOURS", "10")),
    "overnight_max_actions": int(os.getenv("AGENT_SPACE_OVERNIGHT_MAX_ACTIONS", "320")),
    "strict_verification": os.getenv("AGENT_SPACE_STRICT_VERIFICATION", "false").lower() in ("1", "true", "yes"),
    "automation_engine": os.getenv("AGENT_SPACE_AUTOMATION_ENGINE", "open-source"),
    "automation_open_workflows_enabled": os.getenv("AGENT_SPACE_OPEN_WORKFLOWS_ENABLED", "true").lower() in ("1", "true", "yes"),
    "automation_n8n_enabled": os.getenv("AGENT_SPACE_N8N_ENABLED", "false").lower() in ("1", "true", "yes"),
    "automation_n8n_mode": os.getenv("AGENT_SPACE_N8N_MODE", "external"),
    "automation_n8n_url": os.getenv("AGENT_SPACE_N8N_URL", "http://localhost:5678"),
    "automation_n8n_port": int(os.getenv("AGENT_SPACE_N8N_PORT", "5678")),
    "automation_n8n_auto_start": os.getenv("AGENT_SPACE_N8N_AUTO_START", "false").lower() in ("1", "true", "yes"),
    "automation_n8n_stop_on_shutdown": os.getenv("AGENT_SPACE_N8N_STOP_ON_SHUTDOWN", "true").lower() in ("1", "true", "yes"),
    "automation_n8n_start_timeout_seconds": int(os.getenv("AGENT_SPACE_N8N_START_TIMEOUT_SECONDS", "45")),
    "automation_n8n_start_command": os.getenv("AGENT_SPACE_N8N_START_COMMAND", ""),
    "automation_n8n_install_path": os.getenv("AGENT_SPACE_N8N_INSTALL_PATH", ""),
    "builder_open_source_lookup_enabled": os.getenv("AGENT_SPACE_BUILDER_OSS_LOOKUP_ENABLED", "true").lower() in ("1", "true", "yes"),
    "builder_open_source_max_repos": int(os.getenv("AGENT_SPACE_BUILDER_OSS_MAX_REPOS", "3")),
    "free_stack_enabled": os.getenv("AGENT_SPACE_FREE_STACK_ENABLED", "true").lower() in ("1", "true", "yes"),
    "free_stack_env_path": os.getenv("AGENT_SPACE_FREE_STACK_ENV_PATH", ""),
    "free_stack_gotify_enabled": os.getenv("AGENT_SPACE_FREE_STACK_GOTIFY_ENABLED", "false").lower() in ("1", "true", "yes"),
    "free_stack_gotify_url": os.getenv("AGENT_SPACE_FREE_STACK_GOTIFY_URL", ""),
    "free_stack_gotify_token": os.getenv("AGENT_SPACE_FREE_STACK_GOTIFY_TOKEN", ""),
    "agent_models": {},
}


@dataclass
class AgentSpaceRuntimeConfig:
    repo_root: str
    model: str
    command_profile: str
    review_gate: bool
    allow_shell: bool
    max_actions: int
    max_seconds: int
    subagent_retry_attempts: int
    continue_on_subagent_failure: bool
    required_checks: list[str]
    release_gpu_on_off: bool
    backend_port: int
    frontend_port: int
    desktop_mode: bool
    create_git_checkpoint: bool
    run_budget_tokens: int
    proactive_enabled: bool
    proactive_tick_seconds: int
    phone_notifications_enabled: bool
    phone_notification_min_seconds: int
    phone_notifications_on_failure: bool
    auto_self_improve_on_failure_enabled: bool
    auto_self_improve_on_failure_include_stopped: bool
    auto_self_improve_on_failure_cooldown_seconds: int
    auto_self_improve_on_failure_max_per_day: int
    self_learning_enabled: bool
    self_learning_focus: str
    autonomous_web_research_enabled: bool
    chat_auto_web_research_enabled: bool
    run_auto_force_research_enabled: bool
    deep_research_before_build_enabled: bool
    deep_research_min_queries: int
    overnight_autonomy_enabled: bool
    overnight_max_hours: int
    overnight_max_actions: int
    strict_verification: bool
    automation_engine: str
    automation_open_workflows_enabled: bool
    automation_n8n_enabled: bool
    automation_n8n_mode: str
    automation_n8n_url: str
    automation_n8n_port: int
    automation_n8n_auto_start: bool
    automation_n8n_stop_on_shutdown: bool
    automation_n8n_start_timeout_seconds: int
    automation_n8n_start_command: str
    automation_n8n_install_path: str
    builder_open_source_lookup_enabled: bool
    builder_open_source_max_repos: int
    free_stack_enabled: bool
    free_stack_env_path: str
    free_stack_gotify_enabled: bool
    free_stack_gotify_url: str
    free_stack_gotify_token: str
    agent_models: dict[str, str]


class SettingsStore:
    """Thread-safe settings persistence for Agent Space."""

    def __init__(self) -> None:
        ensure_layout()
        self._lock = Lock()
        self._cache = self._load()

    def _load(self) -> dict[str, Any]:
        if not SETTINGS_FILE.exists():
            SETTINGS_FILE.write_text(json.dumps(DEFAULT_SETTINGS, indent=2), encoding="utf-8")
            return dict(DEFAULT_SETTINGS)
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        merged = dict(DEFAULT_SETTINGS)
        merged.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
        return merged

    def get(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._cache)

    def update(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            for key, value in updates.items():
                if key in DEFAULT_SETTINGS:
                    self._cache[key] = value
            SETTINGS_FILE.write_text(json.dumps(self._cache, indent=2), encoding="utf-8")
            return dict(self._cache)

    def as_runtime_config(self) -> AgentSpaceRuntimeConfig:
        cfg = self.get()
        return AgentSpaceRuntimeConfig(
            repo_root=str(DATA_ROOT.parent.parent),
            model=str(cfg["model"]),
            command_profile=str(cfg["command_profile"]),
            review_gate=bool(cfg["review_gate"]),
            allow_shell=bool(cfg["allow_shell"]),
            max_actions=int(cfg["max_actions"]),
            max_seconds=int(cfg["max_seconds"]),
            subagent_retry_attempts=int(cfg.get("subagent_retry_attempts", 2)),
            continue_on_subagent_failure=bool(cfg.get("continue_on_subagent_failure", True)),
            required_checks=list(cfg.get("required_checks", [])),
            release_gpu_on_off=bool(cfg["release_gpu_on_off"]),
            backend_port=int(cfg["backend_port"]),
            frontend_port=int(cfg["frontend_port"]),
            desktop_mode=bool(cfg["desktop_mode"]),
            create_git_checkpoint=bool(cfg["create_git_checkpoint"]),
            run_budget_tokens=int(cfg["run_budget_tokens"]),
            proactive_enabled=bool(cfg.get("proactive_enabled", False)),
            proactive_tick_seconds=int(cfg.get("proactive_tick_seconds", 5)),
            phone_notifications_enabled=bool(cfg.get("phone_notifications_enabled", False)),
            phone_notification_min_seconds=int(cfg.get("phone_notification_min_seconds", 120)),
            phone_notifications_on_failure=bool(cfg.get("phone_notifications_on_failure", True)),
            auto_self_improve_on_failure_enabled=bool(cfg.get("auto_self_improve_on_failure_enabled", True)),
            auto_self_improve_on_failure_include_stopped=bool(cfg.get("auto_self_improve_on_failure_include_stopped", False)),
            auto_self_improve_on_failure_cooldown_seconds=int(cfg.get("auto_self_improve_on_failure_cooldown_seconds", 180)),
            auto_self_improve_on_failure_max_per_day=int(cfg.get("auto_self_improve_on_failure_max_per_day", 12)),
            self_learning_enabled=bool(cfg.get("self_learning_enabled", True)),
            self_learning_focus=str(cfg.get("self_learning_focus", "general")),
            autonomous_web_research_enabled=bool(cfg.get("autonomous_web_research_enabled", True)),
            chat_auto_web_research_enabled=bool(cfg.get("chat_auto_web_research_enabled", True)),
            run_auto_force_research_enabled=bool(cfg.get("run_auto_force_research_enabled", True)),
            deep_research_before_build_enabled=bool(cfg.get("deep_research_before_build_enabled", True)),
            deep_research_min_queries=int(cfg.get("deep_research_min_queries", 3)),
            overnight_autonomy_enabled=bool(cfg.get("overnight_autonomy_enabled", True)),
            overnight_max_hours=int(cfg.get("overnight_max_hours", 10)),
            overnight_max_actions=int(cfg.get("overnight_max_actions", 320)),
            strict_verification=bool(cfg.get("strict_verification", False)),
            automation_engine=str(cfg.get("automation_engine", "open-source")),
            automation_open_workflows_enabled=bool(cfg.get("automation_open_workflows_enabled", True)),
            automation_n8n_enabled=bool(cfg.get("automation_n8n_enabled", False)),
            automation_n8n_mode=str(cfg.get("automation_n8n_mode", "external")),
            automation_n8n_url=str(cfg.get("automation_n8n_url", "http://localhost:5678")),
            automation_n8n_port=int(cfg.get("automation_n8n_port", 5678)),
            automation_n8n_auto_start=bool(cfg.get("automation_n8n_auto_start", False)),
            automation_n8n_stop_on_shutdown=bool(cfg.get("automation_n8n_stop_on_shutdown", True)),
            automation_n8n_start_timeout_seconds=int(cfg.get("automation_n8n_start_timeout_seconds", 45)),
            automation_n8n_start_command=str(cfg.get("automation_n8n_start_command", "")),
            automation_n8n_install_path=str(cfg.get("automation_n8n_install_path", "")),
            builder_open_source_lookup_enabled=bool(cfg.get("builder_open_source_lookup_enabled", True)),
            builder_open_source_max_repos=int(cfg.get("builder_open_source_max_repos", 3)),
            free_stack_enabled=bool(cfg.get("free_stack_enabled", True)),
            free_stack_env_path=str(cfg.get("free_stack_env_path", "")),
            free_stack_gotify_enabled=bool(cfg.get("free_stack_gotify_enabled", False)),
            free_stack_gotify_url=str(cfg.get("free_stack_gotify_url", "")),
            free_stack_gotify_token=str(cfg.get("free_stack_gotify_token", "")),
            agent_models=dict(cfg.get("agent_models", {})),
        )
