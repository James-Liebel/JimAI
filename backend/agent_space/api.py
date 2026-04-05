"""Agent Space API router."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from .rate_limiter import check_run_rate_limit
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from models import ollama_client
from .config import DEFAULT_SETTINGS
from .exporter import export_items
from .api_routes_browser import register_browser_routes
from .api_routes_chat_research import register_chat_research_routes
from .paths import (
    CHATS_DIR,
    DATA_ROOT,
    EXPORTS_DIR,
    INDEX_DIR,
    LOGS_DIR,
    MEMORY_DIR,
    PROJECT_ROOT,
    REVIEWS_DIR,
    RUNTIME_DIR,
    SNAPSHOTS_DIR,
    TEAMS_DIR,
    WORKFLOWS_DIR,
    ensure_layout,
)
from .policies import PolicyError, run_command, validate_command
from .oss_catalog import search_open_source
from .runtime import (
    browser_manager,
    chat_store,
    free_stack_manager,
    instance_lifecycle,
    log_store,
    memory_index_store,
    n8n_manager,
    orchestrator,
    power_manager,
    proactive_engine,
    review_store,
    settings_store,
    snapshot_store,
    skill_store,
    team_store,
    workflow_store,
)
from .web_research import search_web
from .memory_index import IGNORED_DIR_NAMES, TEXT_SUFFIXES

router = APIRouter(prefix="/api/agent-space", tags=["agent-space"])

# Phase modularization: extracted chat/research + browser route groups.
register_chat_research_routes(router, chat_store=chat_store)
register_browser_routes(router, browser_manager=browser_manager)

_SETTINGS_AUDIT_FILE = DATA_ROOT / "settings_audit.jsonl"


def _append_settings_audit(changes: dict[str, Any]) -> None:
    """Append a single audit entry to the settings audit log."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "changes": changes,
        "user": "local",
    }
    try:
        _SETTINGS_AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _SETTINGS_AUDIT_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        logger.warning("Failed to append settings audit entry", exc_info=True)


class RunStartRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=10000)
    autonomous: bool = True

    @field_validator("objective", mode="before")
    @classmethod
    def strip_objective(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
        return v
    team_id: str | None = None
    team: dict[str, Any] | None = None
    allowed_paths: list[str] | None = None
    review_gate: bool | None = None
    allow_shell: bool | None = None
    command_profile: str | None = None
    max_actions: int | None = None
    max_seconds: int | None = None
    subagent_retry_attempts: int | None = None
    continue_on_subagent_failure: bool | None = None
    force_research: bool | None = None
    required_checks: list[str] | None = None
    create_git_checkpoint: bool | None = None
    subagents: list[dict[str, Any]] | None = None
    actions: list[dict[str, Any]] | None = None
    review_scope: str | None = None


class StopRunRequest(BaseModel):
    reason: str = ""


class AssistBaseRequest(BaseModel):
    """Cross-surface assist: ephemeral agents planned by the app to analyze or delegate work."""

    question: str = Field(min_length=1, max_length=12000)
    surface: str = Field(default="general", max_length=64)
    context: str = Field(default="", max_length=50000)
    max_agents: int = Field(default=5, ge=2, le=10)


class AssistSpawnRunRequest(AssistBaseRequest):
    autonomous: bool = True


class PowerUpdateRequest(BaseModel):
    enabled: bool
    release_gpu_on_off: bool | None = None


class SettingsUpdateRequest(BaseModel):
    model: str | None = None
    command_profile: str | None = None
    review_gate: bool | None = None
    allow_shell: bool | None = None
    max_actions: int | None = None
    max_seconds: int | None = None
    subagent_retry_attempts: int | None = None
    continue_on_subagent_failure: bool | None = None
    required_checks: list[str] | None = None
    release_gpu_on_off: bool | None = None
    backend_port: int | None = None
    frontend_port: int | None = None
    desktop_mode: bool | None = None
    create_git_checkpoint: bool | None = None
    run_budget_tokens: int | None = None
    proactive_enabled: bool | None = None
    proactive_tick_seconds: int | None = None
    phone_notifications_enabled: bool | None = None
    phone_notification_min_seconds: int | None = None
    phone_notifications_on_failure: bool | None = None
    auto_self_improve_on_failure_enabled: bool | None = None
    auto_self_improve_on_failure_include_stopped: bool | None = None
    auto_self_improve_on_failure_cooldown_seconds: int | None = None
    auto_self_improve_on_failure_max_per_day: int | None = None
    self_learning_enabled: bool | None = None
    self_learning_focus: str | None = None
    autonomous_web_research_enabled: bool | None = None
    chat_auto_web_research_enabled: bool | None = None
    run_auto_force_research_enabled: bool | None = None
    deep_research_before_build_enabled: bool | None = None
    deep_research_min_queries: int | None = None
    overnight_autonomy_enabled: bool | None = None
    overnight_max_hours: int | None = None
    overnight_max_actions: int | None = None
    strict_verification: bool | None = None
    automation_engine: str | None = None
    automation_open_workflows_enabled: bool | None = None
    automation_n8n_enabled: bool | None = None
    automation_n8n_mode: str | None = None
    automation_n8n_url: str | None = None
    automation_n8n_port: int | None = None
    automation_n8n_auto_start: bool | None = None
    automation_n8n_stop_on_shutdown: bool | None = None
    automation_n8n_start_timeout_seconds: int | None = None
    automation_n8n_start_command: str | None = None
    automation_n8n_install_path: str | None = None
    builder_open_source_lookup_enabled: bool | None = None
    builder_open_source_max_repos: int | None = None
    free_stack_enabled: bool | None = None
    free_stack_env_path: str | None = None
    free_stack_gotify_enabled: bool | None = None
    free_stack_gotify_url: str | None = None
    free_stack_gotify_token: str | None = None
    ollama_url: str | None = None
    anthropic_api_key: str | None = None
    github_token: str | None = None
    agent_models: dict[str, str] | None = None


class RejectRequest(BaseModel):
    reason: str = ""


class ReviewCommitRequest(BaseModel):
    message: str = Field(min_length=3, max_length=300)
    auto_apply: bool = True


class ExportRequest(BaseModel):
    target_folder: str
    include_paths: list[str] = Field(default_factory=list)
    label: str = ""


class ResetDataRequest(BaseModel):
    clear_reviews: bool = True
    clear_runs: bool = True
    clear_snapshots: bool = True
    clear_logs: bool = True
    clear_memory: bool = True
    clear_index: bool = True
    clear_chats: bool = True
    clear_runtime: bool = True
    clear_generated: bool = True
    clear_self_improvement: bool = True
    clear_proactive_goals: bool = True
    clear_teams: bool = False
    clear_exports: bool = False
    clear_workflows: bool = True
    reset_settings: bool = False


class ToolReadRequest(BaseModel):
    path: str


class ToolWriteRequest(BaseModel):
    path: str
    content: str
    review_gate: bool = True


class ToolReplaceRequest(BaseModel):
    path: str
    find: str
    replace: str
    review_gate: bool = True
    count: int = -1


class ToolShellRequest(BaseModel):
    command: str
    cwd: str = "."
    profile: str | None = None
    timeout: int = 120


class WorkspaceTextSearchRequest(BaseModel):
    """Literal substring search across text-like files under the repository (IDE-style find in files)."""

    query: str = Field(..., min_length=1, max_length=500)
    path_prefix: str = ""
    max_results: int = Field(default=150, ge=1, le=500)


class TeamAgentRequest(BaseModel):
    id: str
    role: str = "coder"
    depends_on: list[str] = Field(default_factory=list)
    actions: list[dict[str, Any]] | None = None
    checks: list[str] | None = None
    description: str = ""
    worker_level: int | None = None
    model: str | None = None


class TeamUpsertRequest(BaseModel):
    id: str | None = None
    name: str
    description: str = ""
    agents: list[TeamAgentRequest] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillUpsertRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=1000)
    content: str = ""
    tags: list[str] = Field(default_factory=list)
    complexity: int = Field(default=3, ge=1, le=5)
    source: str = "custom"
    metadata: dict[str, Any] = Field(default_factory=dict)
    slug: str | None = Field(default=None, max_length=120)


class SkillAutoAddRequest(BaseModel):
    objective: str = Field(min_length=4, max_length=10000)
    max_new_skills: int = Field(default=3, ge=1, le=10)


class SkillSelectRequest(BaseModel):
    objective: str = Field(min_length=4, max_length=10000)
    limit: int = Field(default=8, ge=1, le=20)
    include_context: bool = True


class TeamMessageRequest(BaseModel):
    run_id: str = ""
    from_agent: str
    to_agent: str = ""
    channel: str = "general"
    content: str


class RunMessageRequest(BaseModel):
    from_agent: str
    to_agent: str = ""
    channel: str = "general"
    content: str


class InstanceRegisterRequest(BaseModel):
    instance_id: str = ""
    client: str = "ui"
    metadata: dict[str, Any] = Field(default_factory=dict)


class InstanceHeartbeatRequest(BaseModel):
    instance_id: str
    client: str = "ui"
    metadata: dict[str, Any] = Field(default_factory=dict)


class InstanceUnregisterRequest(BaseModel):
    instance_id: str
    reason: str = ""


class ProactiveGoalCreateRequest(BaseModel):
    name: str
    objective: str
    interval_seconds: int = 900
    enabled: bool = True
    run_template: dict[str, Any] = Field(default_factory=dict)


class ProactiveGoalUpdateRequest(BaseModel):
    name: str | None = None
    objective: str | None = None
    interval_seconds: int | None = None
    enabled: bool | None = None
    run_template: dict[str, Any] | None = None
    next_run_at: float | None = None


class SelfImproveSuggestRequest(BaseModel):
    prompt: str = Field(min_length=5, max_length=6000)
    max_suggestions: int = Field(default=8, ge=1, le=20)


class SelfImproveRunRequest(BaseModel):
    prompt: str = Field(min_length=5, max_length=6000)
    confirmed_suggestions: list[str] = Field(default_factory=list)
    direct_prompt_mode: bool = False


class SelfImproveStrengthenRequest(BaseModel):
    prompt: str = Field(min_length=5, max_length=6000)


class N8nStartRequest(BaseModel):
    force: bool = False


class N8nInstallRequest(BaseModel):
    set_as_default: bool = True


class FreeStackNotifyRequest(BaseModel):
    title: str = "jimAI test notification"
    message: str = "jimAI free-stack integration is connected."
    priority: int = 5


class WorkflowUpsertRequest(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    graph: dict[str, Any] = Field(default_factory=dict)
    public_sources: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowRunRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    max_steps: int = Field(default=120, ge=1, le=1000)
    continue_on_error: bool = False


class WorkflowImportN8nRequest(BaseModel):
    workflow_json: dict[str, Any] = Field(default_factory=dict)
    name: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=lambda: ["n8n-import"])


class OpenSourceSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=8, ge=1, le=20)
    min_stars: int = Field(default=20, ge=0, le=500000)
    language: str = ""
    include_unknown_license: bool = False


class BuilderClarifyRequest(BaseModel):
    prompt: str = Field(min_length=5)
    context: str = ""
    max_questions: int = Field(default=6, ge=1, le=12)


class BuilderLaunchRequest(BaseModel):
    prompt: str = Field(min_length=5)
    context: str = ""
    answers: dict[str, str] = Field(default_factory=dict)
    team_name: str = "Auto Build Team"
    save_team: bool = True
    auto_agent_packs: bool = True
    use_saved_teams: bool = True
    review_gate: bool = True
    allow_shell: bool = False
    command_profile: str = "safe"
    required_checks: list[str] = Field(default_factory=list)
    autonomous: bool = True
    max_actions: int | None = None
    max_seconds: int | None = None
    subagent_retry_attempts: int | None = None
    continue_on_subagent_failure: bool | None = None
    force_research: bool | None = None
    create_git_checkpoint: bool | None = None


class BuilderPreviewRequest(BaseModel):
    prompt: str = Field(min_length=1)
    context: str = ""
    team_name: str = "Auto Build Team"
    auto_agent_packs: bool = True
    use_saved_teams: bool = True


def _safe_parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        loaded = json.loads(text)
        if isinstance(loaded, dict):
            return loaded
    except (json.JSONDecodeError, ValueError):
        logger.warning("_safe_parse_json_object: initial JSON parse failed, trying regex extraction", exc_info=True)
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        loaded = json.loads(match.group(0))
        if isinstance(loaded, dict):
            return loaded
    except (json.JSONDecodeError, ValueError):
        return None
    return None


def _fallback_builder_questions(prompt: str, max_questions: int) -> list[str]:
    base = [
        "What platform do you want first: web app, desktop app, mobile app, or API service?",
        "What tech stack should be used (frontend, backend, database), or should the system choose?",
        "What core features are required for v1, and what can wait for later?",
        "Do you need auth/roles, and if yes which providers or local auth style?",
        "What deployment/export target should be prepared (Docker, Vercel, separate repo folder, etc.)?",
        "What constraints matter most (speed, security, offline support, design style, budget)?",
    ]
    text = prompt.lower()
    if "saas" in text:
        base.insert(3, "Do you need billing/subscriptions (Stripe/Paddle), and what plans should exist?")
    if "ai" in text or "agent" in text:
        base.insert(2, "Which model providers/modes are allowed (local-only Ollama is default) and what tools should agents use?")
    return base[: max(1, max_questions)]


def _normalize_suggestion_texts(items: list[str], *, max_items: int) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = " ".join(str(item or "").strip().split())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
        if len(cleaned) >= max(1, max_items):
            break
    return cleaned


def _specificify_suggestion(text: str, prompt: str) -> str:
    cleaned = " ".join(str(text or "").strip().split())
    if not cleaned:
        return ""
    lower = cleaned.lower()
    has_target_signal = any(
        token in lower
        for token in (
            "frontend/",
            "backend/",
            "page",
            "endpoint",
            "workflow",
            "review",
            "builder",
            "self-code",
            "settings",
            "metric",
            "event",
            "summary",
            "retry",
        )
    )
    if has_target_signal and len(cleaned.split()) >= 8:
        return cleaned
    prompt_hint = " ".join(str(prompt or "").strip().split())[:90]
    return (
        f"{cleaned} Target: Improve this scope -> {prompt_hint}. "
        "Expected result: measurable reliability or UX gain."
    ).strip()


def _specificify_suggestions(items: list[str], prompt: str, *, max_items: int) -> list[str]:
    specific = [_specificify_suggestion(item, prompt) for item in items]
    return _normalize_suggestion_texts(specific, max_items=max_items)


def _fallback_self_improve_suggestions(prompt: str, focus: str, *, max_items: int) -> list[str]:
    prompt_hint = str(prompt or "").strip()
    base = [
        (
            "Improve `frontend/src/pages/SelfCode.tsx` so users can run prompt-direct or "
            "suggestion-confirmed flows with clear disabled states and completion feedback."
        ),
        (
            "Improve `backend/agent_space/orchestrator.py` action resilience by retrying failed "
            "recoverable actions and applying fallback methods before marking failure."
        ),
        (
            "Add automatic run-completion summaries that include status, action count, "
            "review/snapshot outputs, and confirmed self-improve goals."
        ),
        (
            "Improve planner and verifier handoff quality by requiring specific follow-up messages "
            "with actionable checks for unresolved risks."
        ),
        (
            f"Prioritize self-learning focus `{focus}` with concrete file/endpoint targets "
            "and acceptance checks in each proposal."
        ),
        (
            f"Strengthen build reliability for this request scope: {prompt_hint}. "
            "Target result: fewer failed runs and faster autonomous completion."
        ),
    ]
    return _specificify_suggestions(base, prompt_hint, max_items=max_items)


async def _generate_self_improve_suggestions(prompt: str, max_suggestions: int) -> dict[str, Any]:
    settings = settings_store.get()
    model = str(settings.get("model", "qwen2.5-coder:14b"))
    focus = str(settings.get("self_learning_focus", "general"))
    fallback = _fallback_self_improve_suggestions(prompt, focus, max_items=max_suggestions)
    suggestions = list(fallback)
    autonomous_notes: list[str] = []

    llm_prompt = (
        "You are generating improvement proposals for a local autonomous coding platform.\n"
        "Propose practical, high-impact self-improvements for the current repository.\n"
        "Suggestions must be relatively specific: include target component/file/flow and expected outcome.\n"
        "Return strict JSON object only with keys:\n"
        "suggestions: array of short strings\n"
        "autonomous_notes: array of short strings\n"
        f"Limit suggestions to at most {max_suggestions}.\n\n"
        f"User self-improvement prompt:\n{prompt.strip()}\n\n"
        f"Current self-learning focus: {focus}\n"
    )
    try:
        text = await ollama_client.chat_full(
            model=model,
            messages=[
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": llm_prompt},
            ],
            temperature=0.2,
        )
        parsed = _safe_parse_json_object(text) or {}
        raw_suggestions = parsed.get("suggestions") if isinstance(parsed, dict) else []
        raw_notes = parsed.get("autonomous_notes") if isinstance(parsed, dict) else []
        merged: list[str] = []
        if isinstance(raw_suggestions, list):
            for item in raw_suggestions:
                merged.append(str(item or ""))
        merged.extend(fallback)
        suggestions = _specificify_suggestions(merged, prompt, max_items=max_suggestions)
        if isinstance(raw_notes, list):
            autonomous_notes = _normalize_suggestion_texts([str(item or "") for item in raw_notes], max_items=8)
    except Exception:
        suggestions = fallback
        autonomous_notes = []

    return {
        "model": model,
        "focus": focus,
        "suggestions": suggestions,
        "autonomous_notes": autonomous_notes,
    }


async def _stream_self_improve_suggestions(
    prompt: str,
    max_suggestions: int,
    request: Request,
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream NDJSON events for suggest: meta, action, chunk, progress, then result (or stopped)."""
    settings = settings_store.get()
    model = str(settings.get("model", "qwen2.5-coder:14b"))
    focus = str(settings.get("self_learning_focus", "general"))
    fallback = _fallback_self_improve_suggestions(prompt, focus, max_items=max_suggestions)
    yield {"type": "meta", "model": model, "focus": focus}
    yield {"type": "action", "stage": "ollama", "label": "Calling local model (streaming)…"}

    llm_prompt = (
        "You are generating improvement proposals for a local autonomous coding platform.\n"
        "Propose practical, high-impact self-improvements for the current repository.\n"
        "Suggestions must be relatively specific: include target component/file/flow and expected outcome.\n"
        "Return strict JSON object only with keys:\n"
        "suggestions: array of short strings\n"
        "autonomous_notes: array of short strings\n"
        f"Limit suggestions to at most {max_suggestions}.\n\n"
        f"User self-improvement prompt:\n{prompt.strip()}\n\n"
        f"Current self-learning focus: {focus}\n"
    )
    parts: list[str] = []
    progress_mark = 0
    try:
        async for piece in ollama_client.chat_stream(
            model=model,
            messages=[
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": llm_prompt},
            ],
            temperature=0.2,
        ):
            parts.append(piece)
            yield {"type": "chunk", "text": piece}
            total_chars = sum(len(p) for p in parts)
            if total_chars - progress_mark >= 4096:
                progress_mark = total_chars
                yield {"type": "progress", "chars": total_chars}
            if await request.is_disconnected():
                yield {"type": "stopped", "reason": "client_disconnected", "partial_chars": total_chars}
                return
    except asyncio.CancelledError:
        yield {
            "type": "stopped",
            "reason": "cancelled",
            "partial_chars": sum(len(p) for p in parts),
        }
        raise

    yield {"type": "action", "stage": "parse", "label": "Parsing JSON response…"}
    text = "".join(parts)
    suggestions = list(fallback)
    autonomous_notes: list[str] = []
    try:
        parsed = _safe_parse_json_object(text) or {}
        raw_suggestions = parsed.get("suggestions") if isinstance(parsed, dict) else []
        raw_notes = parsed.get("autonomous_notes") if isinstance(parsed, dict) else []
        merged: list[str] = []
        if isinstance(raw_suggestions, list):
            for item in raw_suggestions:
                merged.append(str(item or ""))
        merged.extend(fallback)
        suggestions = _specificify_suggestions(merged, prompt, max_items=max_suggestions)
        if isinstance(raw_notes, list):
            autonomous_notes = _normalize_suggestion_texts([str(item or "") for item in raw_notes], max_items=8)
    except Exception:
        suggestions = fallback
        autonomous_notes = []

    suggestion_rows = [
        {"id": f"suggestion-{idx + 1}", "text": str(t), "source": "autonomous"}
        for idx, t in enumerate(suggestions)
    ]
    yield {
        "type": "result",
        "prompt": prompt,
        "model": model,
        "focus": focus,
        "requires_confirmation": True,
        "autonomous_notes": autonomous_notes,
        "suggestions": suggestion_rows,
    }


async def _strengthen_self_improve_prompt(prompt: str) -> dict[str, Any]:
    """Use the configured local model to rewrite a vague user request into a clearer self-improve instruction."""
    settings = settings_store.get()
    model = str(settings.get("model", "qwen2.5-coder:14b"))
    cleaned = str(prompt or "").strip()
    llm_user = (
        "Rewrite the following user request into a single clear instruction for an autonomous coding agent "
        "improving this repository (jimAI: FastAPI agent orchestration + React frontend). "
        "Keep the user's goals; add concrete scope, acceptance hints, and file/area targets when reasonable. "
        'Return strict JSON only with key "strengthened_prompt" (string).\n\n'
        f"User request:\n{cleaned}"
    )
    try:
        text = await ollama_client.chat_full(
            model=model,
            messages=[
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": llm_user},
            ],
            temperature=0.2,
        )
        parsed = _safe_parse_json_object(text) or {}
        strengthened = str(parsed.get("strengthened_prompt") or "").strip()
        if not strengthened:
            strengthened = cleaned
        return {"strengthened_prompt": strengthened, "model": model}
    except Exception:
        return {"strengthened_prompt": cleaned, "model": model}


def _fallback_builder_team() -> list[dict[str, Any]]:
    return [
        {
            "id": "planner",
            "role": "planner",
            "depends_on": [],
            "description": "Define implementation plan, milestones, and architecture for the requested app.",
            "actions": [
                {"type": "send_message", "to": "architect", "channel": "handoff", "content": "Plan drafted. Build architecture and contracts."}
            ],
        },
        {
            "id": "architect",
            "role": "coder",
            "depends_on": ["planner"],
            "description": "Design folder structure, interfaces, and integration contracts.",
            "actions": [
                {"type": "read_messages", "channel": "handoff"},
                {"type": "send_message", "to": "builder", "channel": "handoff", "content": "Architecture ready. Implement app components and flows."},
            ],
        },
        {
            "id": "builder",
            "role": "coder",
            "depends_on": ["architect"],
            "description": "Implement end-to-end application changes across frontend/backend/module code.",
            "actions": [
                {"type": "read_messages", "channel": "handoff"},
                {"type": "send_message", "to": "tester", "channel": "handoff", "content": "Implementation completed. Validate and run checks."},
            ],
        },
        {
            "id": "tester",
            "role": "tester",
            "depends_on": ["builder"],
            "description": "Run required checks and ensure behavior and edge cases are covered.",
            "actions": [
                {"type": "read_messages", "channel": "handoff"},
                {"type": "send_message", "to": "packager", "channel": "handoff", "content": "Validation done. Prepare export package."},
            ],
        },
        {
            "id": "packager",
            "role": "coder",
            "depends_on": ["tester"],
            "description": "Prepare export paths and deployment-ready handoff artifacts.",
            "actions": [{"type": "read_messages", "channel": "handoff"}],
        },
    ]


def _fallback_assist_agents(surface: str) -> list[dict[str, Any]]:
    return [
        {
            "id": "context-analyst",
            "role": "planner",
            "depends_on": [],
            "description": f"Interpret the question in the context of UI surface '{surface}' and extract concrete sub-problems.",
        },
        {
            "id": "technical-reviewer",
            "role": "coder",
            "depends_on": ["context-analyst"],
            "description": "Reason about implementation, architecture, risks, and repository-relevant details.",
        },
        {
            "id": "answer-synthesizer",
            "role": "verifier",
            "depends_on": ["technical-reviewer"],
            "description": "Merge findings into a clear, actionable answer for the user.",
        },
    ]


def _normalize_assist_agent_rows(raw: Any, *, max_agents: int) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in raw[: max(2, max_agents)]:
        if not isinstance(row, dict):
            continue
        agent_id = str(row.get("id") or "").strip()
        if not agent_id or agent_id in seen:
            continue
        role = str(row.get("role") or "coder").strip().lower()
        if role not in ("planner", "coder", "tester", "verifier"):
            role = "coder"
        deps = [str(d).strip() for d in list(row.get("depends_on") or []) if str(d).strip()]
        desc = str(row.get("description") or "").strip()
        out.append(
            {
                "id": agent_id,
                "role": role,
                "depends_on": deps,
                "description": desc or f"Assist agent {agent_id}",
            }
        )
        seen.add(agent_id)
    return out


async def _generate_assist_team(
    question: str,
    surface: str,
    context: str,
    model: str,
    max_agents: int,
) -> tuple[list[dict[str, Any]], str]:
    """LLM-planned ephemeral agents + one-line delegate objective; safe fallback."""
    cap = max(2, min(10, max_agents))
    plan_prompt = (
        "You configure ephemeral AI subagents inside jimAI (local FastAPI + React IDE).\n"
        f'The user is on surface "{surface}" (e.g. chat, builder, self-code, automation, agents).\n'
        "Return strict JSON only with keys:\n"
        '  agents: array of { id, role, depends_on, description }\n'
        '  delegate_objective: one sentence describing what autonomous repo work would accomplish (may be non-code if Q&A only)\n'
        f"Use between 2 and {cap} agents. Unique ids, acyclic depends_on. "
        "roles must be one of: planner, coder, tester, verifier.\n\n"
        f"Question:\n{question}\n\n"
        f"Optional user/context:\n{context or '(none)'}\n"
    )
    delegate = "Clarify and answer the user's question with repository-aware guidance when relevant."
    try:
        text = await ollama_client.chat_full(
            model=model,
            messages=[
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": plan_prompt},
            ],
            temperature=0.25,
        )
        parsed = _safe_parse_json_object(text) or {}
        raw_agents = parsed.get("agents") if isinstance(parsed, dict) else None
        cand = _normalize_assist_agent_rows(raw_agents, max_agents=cap)
        if len(cand) >= 2:
            d = str((parsed.get("delegate_objective") if isinstance(parsed, dict) else "") or "").strip()
            if d:
                delegate = d
            return cand, delegate
    except Exception:
        logger.warning("assist: failed to plan agents via LLM", exc_info=True)
    return _fallback_assist_agents(surface), delegate


def _assist_specialist_system_preamble(agents: list[dict[str, Any]], surface: str) -> str:
    lines = [
        "You are a coordinated panel of specialists answering ONE user question in a single response.",
        f"Current UI surface: {surface}.",
        "Specialists (use their perspectives; write as one cohesive answer):",
    ]
    for row in agents:
        aid = str(row.get("id", ""))
        role = str(row.get("role", ""))
        desc = str(row.get("description", ""))
        lines.append(f"- {aid} ({role}): {desc}")
    lines.append(
        "Structure: brief per-lens bullets if helpful, then a short merged conclusion. "
        "Be accurate; if uncertain, say so. Prefer concrete steps for this codebase when relevant."
    )
    return "\n".join(lines)


async def _stream_assist_analyze(
    question: str,
    surface: str,
    context: str,
    max_agents: int,
    request: Request,
) -> AsyncGenerator[dict[str, Any], None]:
    settings = settings_store.get()
    model = str(settings.get("model", "qwen2.5-coder:14b"))
    agents, delegate_objective = await _generate_assist_team(question, surface, context, model, max_agents)
    yield {
        "type": "meta",
        "model": model,
        "surface": surface,
        "agents": [
            {
                "id": str(a.get("id", "")),
                "role": str(a.get("role", "")),
                "depends_on": list(a.get("depends_on") or []),
                "description": str(a.get("description", "")),
            }
            for a in agents
        ],
        "delegate_objective": delegate_objective,
    }
    yield {"type": "action", "stage": "answer", "label": "Streaming multi-agent answer…"}
    user_block = f"Question:\n{question}\n"
    if context.strip():
        user_block += f"\nAdditional context:\n{context.strip()}\n"
    user_block += f"\nIf autonomous coding could help beyond this chat, note: {delegate_objective}"
    messages = [
        {"role": "system", "content": _assist_specialist_system_preamble(agents, surface)},
        {"role": "user", "content": user_block},
    ]
    try:
        async for piece in ollama_client.chat_stream(
            model=model,
            messages=messages,
            temperature=0.35,
        ):
            yield {"type": "chunk", "text": piece}
            if await request.is_disconnected():
                yield {"type": "stopped", "reason": "client_disconnected"}
                return
    except asyncio.CancelledError:
        yield {"type": "stopped", "reason": "cancelled"}
        raise
    except Exception as exc:
        yield {"type": "error", "message": str(exc)}
        return
    yield {"type": "done"}


AGENT_PACK_LIBRARY: dict[str, list[dict[str, Any]]] = {
    "ui": [
        {
            "id": "ui-designer",
            "role": "coder",
            "depends_on": ["planner"],
            "description": "Own UX flows, responsive UI behavior, and accessibility checks.",
            "actions": [{"type": "send_message", "to": "builder", "channel": "handoff", "content": "UI direction and acceptance criteria prepared."}],
        }
    ],
    "mobile": [
        {
            "id": "mobile-qa",
            "role": "tester",
            "depends_on": ["builder"],
            "description": "Validate mobile UX, touch interactions, and responsive layout.",
            "actions": [{"type": "send_message", "to": "tester", "channel": "handoff", "content": "Mobile checks completed and findings shared."}],
        }
    ],
    "security": [
        {
            "id": "security-reviewer",
            "role": "tester",
            "depends_on": ["builder"],
            "description": "Review auth/data handling and common web security issues.",
            "actions": [{"type": "send_message", "to": "tester", "channel": "handoff", "content": "Security review summary ready."}],
        }
    ],
    "data": [
        {
            "id": "data-engineer",
            "role": "coder",
            "depends_on": ["architect"],
            "description": "Design data models, migrations, and analytics/reporting paths.",
            "actions": [{"type": "send_message", "to": "builder", "channel": "handoff", "content": "Data layer plan and schemas prepared."}],
        }
    ],
    "devops": [
        {
            "id": "devops-packager",
            "role": "coder",
            "depends_on": ["tester"],
            "description": "Prepare deployment/export packaging and runtime ops notes.",
            "actions": [{"type": "send_message", "to": "packager", "channel": "handoff", "content": "Deployment and packaging checklist completed."}],
        }
    ],
}


def _simple_tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) >= 3}


def _derive_agent_packs(prompt: str, context: str) -> list[str]:
    text = f"{prompt}\n{context}".lower()
    packs: list[str] = []
    if any(k in text for k in ("ui", "design", "dashboard", "frontend", "ux")):
        packs.append("ui")
    if any(k in text for k in ("mobile", "phone", "responsive", "pwa")):
        packs.append("mobile")
    if any(k in text for k in ("auth", "security", "compliance", "permission", "privacy")):
        packs.append("security")
    if any(k in text for k in ("database", "analytics", "report", "data", "etl", "vector")):
        packs.append("data")
    if any(k in text for k in ("deploy", "docker", "kubernetes", "pipeline", "ci", "cd", "export")):
        packs.append("devops")
    return packs


def _merge_team_agents(
    base_agents: list[dict[str, Any]],
    extra_agents: list[dict[str, Any]],
    *,
    max_agents: int = 12,
) -> list[dict[str, Any]]:
    merged = [dict(row) for row in base_agents]
    existing = {str(row.get("id") or "").strip() for row in merged if str(row.get("id") or "").strip()}
    for row in extra_agents:
        if len(merged) >= max_agents:
            break
        if not isinstance(row, dict):
            continue
        raw_id = str(row.get("id") or "").strip() or "agent"
        candidate_id = raw_id
        n = 2
        while candidate_id in existing:
            candidate_id = f"{raw_id}-{n}"
            n += 1
        copied = dict(row)
        copied["id"] = candidate_id
        copied["depends_on"] = [str(dep) for dep in list(copied.get("depends_on") or []) if str(dep).strip()]
        merged.append(copied)
        existing.add(candidate_id)
    return merged


def _select_saved_team_agents(prompt: str, context: str, *, max_teams: int = 1) -> tuple[list[dict[str, Any]], list[str]]:
    rows = team_store.list_teams(limit=200)
    query_tokens = _simple_tokens(f"{prompt}\n{context}")
    if not query_tokens:
        return [], []
    scored: list[tuple[int, dict[str, Any]]] = []
    for team in rows:
        corpus = f"{team.get('name', '')} {team.get('description', '')}"
        score = len(query_tokens.intersection(_simple_tokens(corpus)))
        if score > 0:
            scored.append((score, team))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected_names: list[str] = []
    selected_agents: list[dict[str, Any]] = []
    for _, team in scored[: max(1, max_teams)]:
        selected_names.append(str(team.get("name") or team.get("id") or "saved-team"))
        selected_agents.extend(list(team.get("agents") or []))
    return selected_agents, selected_names


def _augment_builder_team(
    base_agents: list[dict[str, Any]],
    *,
    prompt: str,
    context: str,
    use_saved_teams: bool,
    auto_agent_packs: bool,
    max_agents: int = 12,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    team_agents = [dict(row) for row in base_agents]
    used_saved_teams: list[str] = []
    used_agent_packs: list[str] = []

    if use_saved_teams:
        saved_agents, saved_team_names = _select_saved_team_agents(prompt, context, max_teams=1)
        if saved_agents:
            team_agents = _merge_team_agents(team_agents, saved_agents, max_agents=max_agents)
            used_saved_teams = saved_team_names

    if auto_agent_packs:
        used_agent_packs = _derive_agent_packs(prompt, context)
        for pack_name in used_agent_packs:
            team_agents = _merge_team_agents(
                team_agents,
                AGENT_PACK_LIBRARY.get(pack_name, []),
                max_agents=max_agents,
            )

    return team_agents, used_saved_teams, used_agent_packs


def _build_launch_objective(prompt: str, context: str, answers: dict[str, str]) -> str:
    answer_lines = []
    for key, value in answers.items():
        v = str(value or "").strip()
        if not v:
            continue
        answer_lines.append(f"- {key}: {v}")
    lines = [
        "Build a full end-to-end application in this repository based on the user request.",
        "",
        "Primary request:",
        prompt.strip(),
    ]
    if context.strip():
        lines.extend(["", "Additional context:", context.strip()])
    if answer_lines:
        lines.extend(["", "Clarification answers:", *answer_lines])
    lines.extend(
        [
            "",
            "Execution requirements:",
            "- Create and coordinate subagents as needed for planning, implementation, testing, and packaging.",
            "- Prefer review-gated diffs over direct writes unless explicitly needed.",
            "- Keep changes modular and production-leaning.",
            "- Include/update tests or validation steps when possible.",
            "- House generated app outputs under data/app_creations/<app_name>/.",
            "- Update data/app_creations/APP_CREATIONS.md with each new app build summary.",
            "- Prepare output so modules/apps can be exported for separate deployment repos.",
        ]
    )
    return "\n".join(lines).strip()


def _resolve_repo_path(path_text: str) -> tuple[str, Path]:
    p = Path(path_text)
    if p.is_absolute():
        abs_path = p.resolve()
    else:
        abs_path = (PROJECT_ROOT / p).resolve()
    if not str(abs_path).startswith(str(PROJECT_ROOT.resolve())):
        raise HTTPException(status_code=400, detail="Path is outside repository.")
    return abs_path.relative_to(PROJECT_ROOT).as_posix(), abs_path


def _run_git(args: list[str]) -> tuple[int, str, str]:
    process = subprocess.run(
        args,
        cwd=str(PROJECT_ROOT),
        text=True,
        capture_output=True,
    )
    return process.returncode, process.stdout.strip(), process.stderr.strip()


def _commit_review_paths(paths: list[str], message: str) -> dict[str, Any]:
    commit_message = message.strip()
    if not commit_message:
        raise RuntimeError("Commit message is required.")

    code, stdout, stderr = _run_git(["git", "rev-parse", "--is-inside-work-tree"])
    if code != 0 or stdout.lower() != "true":
        raise RuntimeError("Current repository is not a git working tree.")

    safe_paths: list[str] = []
    for raw_path in paths:
        rel_path = str(raw_path or "").replace("\\", "/").strip().lstrip("/")
        if not rel_path:
            continue
        abs_path = (PROJECT_ROOT / rel_path).resolve()
        if not str(abs_path).startswith(str(PROJECT_ROOT.resolve())):
            continue
        safe_paths.append(rel_path)
    safe_paths = sorted(set(safe_paths))
    if not safe_paths:
        raise RuntimeError("No changed files were found for this review.")

    add_code, add_stdout, add_stderr = _run_git(["git", "add", "--all", "--", *safe_paths])
    if add_code != 0:
        raise RuntimeError(f"git add failed: {add_stderr or add_stdout or 'unknown error'}")

    staged_code, staged_stdout, staged_stderr = _run_git(["git", "diff", "--cached", "--name-only", "--", *safe_paths])
    if staged_code != 0:
        raise RuntimeError(f"Failed to inspect staged files: {staged_stderr or staged_stdout or 'unknown error'}")
    staged_files = [line.strip().replace("\\", "/") for line in staged_stdout.splitlines() if line.strip()]
    if not staged_files:
        raise RuntimeError("No staged changes for this review. Apply changes before committing.")

    commit_code, commit_stdout, commit_stderr = _run_git(["git", "commit", "-m", commit_message])
    if commit_code != 0:
        detail = (commit_stderr or commit_stdout or "git commit failed").strip()
        raise RuntimeError(detail)

    hash_code, hash_stdout, hash_stderr = _run_git(["git", "rev-parse", "--short", "HEAD"])
    commit_id = hash_stdout.strip() if hash_code == 0 else ""

    return {
        "commit_id": commit_id,
        "message": commit_message,
        "files": staged_files,
        "git_output": commit_stdout.strip(),
        "git_error": hash_stderr.strip() if hash_code != 0 else "",
    }


def _build_repo_tree(
    *,
    root_abs: Path,
    root_rel: str,
    depth: int,
    limit: int,
    include_hidden: bool,
) -> dict[str, Any]:
    scanned = 0
    truncated = False

    def _walk(path: Path, rel_path: str, level: int) -> dict[str, Any]:
        nonlocal scanned, truncated
        is_dir = path.is_dir()
        node: dict[str, Any] = {
            "name": path.name if rel_path else ".",
            "path": rel_path or ".",
            "type": "directory" if is_dir else "file",
        }
        if (not is_dir) or level >= depth or truncated:
            return node

        children: list[dict[str, Any]] = []
        try:
            entries = sorted(
                path.iterdir(),
                key=lambda entry: (not entry.is_dir(), entry.name.lower()),
            )
        except Exception:
            node["children"] = children
            return node

        for entry in entries:
            if not include_hidden and entry.name.startswith("."):
                continue
            scanned += 1
            if scanned > limit:
                truncated = True
                break
            child_rel = f"{rel_path}/{entry.name}" if rel_path else entry.name
            children.append(_walk(entry, child_rel, level + 1))
            if truncated:
                break

        node["children"] = children
        return node

    root_display = "" if root_rel == "." else root_rel
    tree = _walk(root_abs, root_display, 0)
    return {
        "root": root_display or ".",
        "depth": depth,
        "limit": limit,
        "scanned": scanned,
        "truncated": truncated,
        "tree": tree,
    }


def _stream(queue: asyncio.Queue) -> StreamingResponse:
    async def _generator() -> AsyncGenerator[str, None]:
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(payload)}\n\n"
            except asyncio.TimeoutError:
                yield "data: {\"type\":\"keepalive\"}\n\n"

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _clear_dir(path: Path) -> int:
    removed = 0
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        return removed
    for child in list(path.iterdir()):
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
            removed += 1
        except Exception:
            continue
    path.mkdir(parents=True, exist_ok=True)
    return removed


def _safe_write_json(path: Path, payload: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.warning("_safe_write_json: failed to write JSON to '%s'", path, exc_info=True)


def _audit_check(
    check_id: str,
    title: str,
    status: str,
    summary: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "title": title,
        "status": status,
        "summary": summary,
        "details": details or {},
    }


def _audit_overall_status(checks: list[dict[str, Any]]) -> str:
    statuses = [str(row.get("status", "")) for row in checks]
    if any(status == "fail" for status in statuses):
        return "fail"
    if any(status == "warn" for status in statuses):
        return "warn"
    return "pass"


async def _run_system_audit(
    *,
    include_research_probe: bool = False,
    include_browser_probe: bool = False,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    now = time.time()
    settings = settings_store.get()
    power = power_manager.get_state()

    power_enabled = bool(power.get("enabled", True))
    checks.append(
        _audit_check(
            "power",
            "System Power",
            "pass" if power_enabled else "warn",
            "Power is ON." if power_enabled else "Power is OFF. New runs are blocked.",
            {"enabled": power_enabled, "release_gpu_on_off": bool(power.get("release_gpu_on_off", False))},
        )
    )

    settings_errors: list[str] = []
    settings_warnings: list[str] = []
    profile = str(settings.get("command_profile", "safe"))
    if profile not in {"safe", "dev", "unrestricted"}:
        settings_errors.append(f"Invalid command_profile '{profile}'.")
    try:
        max_actions = int(settings.get("max_actions", 40))
    except (TypeError, ValueError):
        max_actions = 0
        settings_errors.append("max_actions is not an integer.")
    try:
        max_seconds = int(settings.get("max_seconds", 1200))
    except (TypeError, ValueError):
        max_seconds = 0
        settings_errors.append("max_seconds is not an integer.")
    if max_actions < 1:
        settings_errors.append("max_actions must be >= 1.")
    if max_seconds < 30:
        settings_warnings.append("max_seconds is very low (<30s).")
    if not bool(settings.get("review_gate", True)):
        settings_warnings.append("review_gate is OFF.")
    if bool(settings.get("allow_shell", False)) and profile == "unrestricted":
        settings_warnings.append("allow_shell + unrestricted profile is high-risk.")
    checks.append(
        _audit_check(
            "settings",
            "Runtime Settings",
            "fail" if settings_errors else ("warn" if settings_warnings else "pass"),
            "Settings are coherent." if not settings_errors and not settings_warnings else "Settings need attention.",
            {
                "errors": settings_errors,
                "warnings": settings_warnings,
                "model": str(settings.get("model", "")),
                "command_profile": profile,
                "max_actions": max_actions,
                "max_seconds": max_seconds,
            },
        )
    )

    path_errors: list[str] = []
    touched = False
    required_paths = [PROJECT_ROOT, DATA_ROOT, REVIEWS_DIR, SNAPSHOTS_DIR, LOGS_DIR, MEMORY_DIR, INDEX_DIR, RUNTIME_DIR]
    for path in required_paths:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            path_errors.append(f"{path}: {exc}")
    probe_file = RUNTIME_DIR / ".system_audit_write_probe.tmp"
    try:
        probe_file.write_text("ok", encoding="utf-8")
        touched = True
    except Exception as exc:
        path_errors.append(f"{probe_file}: {exc}")
    finally:
        if touched:
            try:
                probe_file.unlink(missing_ok=True)
            except Exception:
                logger.warning("Failed to remove system audit write probe file '%s'", probe_file, exc_info=True)
    checks.append(
        _audit_check(
            "storage",
            "Storage Layout",
            "fail" if path_errors else "pass",
            "Storage paths are readable/writable." if not path_errors else "Some storage paths are not writable.",
            {"path_errors": path_errors},
        )
    )

    try:
        models = await ollama_client.list_models()
        default_model = str(settings.get("model", "qwen2.5-coder:14b"))
        model_status = "pass"
        summary = f"Ollama reachable with {len(models)} local model(s)."
        if not models:
            model_status = "fail"
            summary = "Ollama reachable but no models were found."
        elif default_model not in models:
            model_status = "warn"
            summary = "Default model is missing from local Ollama models."
        checks.append(
            _audit_check(
                "ollama",
                "Local Model Runtime (Ollama)",
                model_status,
                summary,
                {"default_model": default_model, "models": models[:50]},
            )
        )
    except Exception as exc:
        checks.append(
            _audit_check(
                "ollama",
                "Local Model Runtime (Ollama)",
                "fail",
                "Could not connect to Ollama.",
                {"error": str(exc)},
            )
        )

    run_rows = orchestrator.list_runs(limit=500)
    running = [row for row in run_rows if str(row.get("status")) == "running"]
    stale_threshold = max(120, int(settings.get("max_seconds", 1200)) * 2)
    stale_runs: list[str] = []
    for row in running:
        started_at = float(row.get("started_at") or row.get("created_at") or 0)
        if started_at > 0 and (now - started_at) > stale_threshold:
            stale_runs.append(str(row.get("id", "")))
    checks.append(
        _audit_check(
            "run-health",
            "Run Health",
            "warn" if stale_runs else "pass",
            "No stale running runs detected." if not stale_runs else "Potentially stale running runs detected.",
            {
                "total_runs": len(run_rows),
                "running_count": len(running),
                "stale_threshold_seconds": stale_threshold,
                "stale_run_ids": stale_runs[:25],
            },
        )
    )

    store_errors: list[str] = []
    store_counts: dict[str, int] = {}
    try:
        store_counts["reviews"] = len(review_store.list_reviews(limit=2000))
    except Exception as exc:
        store_errors.append(f"reviews: {exc}")
    try:
        store_counts["snapshots"] = len(snapshot_store.list_snapshots(limit=500))
    except Exception as exc:
        store_errors.append(f"snapshots: {exc}")
    try:
        store_counts["teams"] = len(team_store.list_teams(limit=2000))
    except Exception as exc:
        store_errors.append(f"teams: {exc}")
    try:
        store_counts["memory_recent"] = len(memory_index_store.list_recent_runs(limit=200))
    except Exception as exc:
        store_errors.append(f"memory: {exc}")
    checks.append(
        _audit_check(
            "stores",
            "State Stores",
            "fail" if store_errors else "pass",
            "State stores are readable." if not store_errors else "Some state stores could not be read.",
            {"counts": store_counts, "errors": store_errors},
        )
    )

    policy_errors: list[str] = []
    try:
        validate_command(
            command="python --version",
            profile="safe",
            cwd=str(PROJECT_ROOT),
            repo_root=PROJECT_ROOT,
            allow_shell=True,
        )
    except Exception as exc:
        policy_errors.append(f"safe profile blocked baseline command: {exc}")

    chaining_blocked = False
    try:
        validate_command(
            command="git status && echo test",
            profile="safe",
            cwd=str(PROJECT_ROOT),
            repo_root=PROJECT_ROOT,
            allow_shell=True,
        )
    except Exception:
        chaining_blocked = True
    if not chaining_blocked:
        policy_errors.append("safe profile allowed command chaining with &&.")

    checks.append(
        _audit_check(
            "policy",
            "Command Policy",
            "fail" if policy_errors else "pass",
            "Policy smoke checks passed." if not policy_errors else "Policy smoke checks failed.",
            {"errors": policy_errors},
        )
    )

    if include_research_probe:
        probe = await search_web("agentic software engineering workflow reliability", limit=1)
        checks.append(
            _audit_check(
                "web-research",
                "Web Research Probe",
                "pass" if bool(probe.get("ok")) else "warn",
                "Web research probe succeeded." if bool(probe.get("ok")) else "Web research probe failed (offline or blocked).",
                {
                    "ok": bool(probe.get("ok")),
                    "offline": bool(probe.get("offline")),
                    "result_count": len(list(probe.get("results") or [])),
                    "error": str(probe.get("error", ""))[:200],
                },
            )
        )
    else:
        checks.append(
            _audit_check(
                "web-research",
                "Web Research Probe",
                "info",
                "Skipped (enable include_research_probe to run).",
            )
        )

    if include_browser_probe:
        try:
            sessions = await browser_manager.list_sessions()
            checks.append(
                _audit_check(
                    "browser",
                    "Browser Agent Probe",
                    "pass",
                    "Browser manager reachable.",
                    {"session_count": len(sessions)},
                )
            )
        except Exception as exc:
            checks.append(
                _audit_check(
                    "browser",
                    "Browser Agent Probe",
                    "warn",
                    "Browser manager probe failed (possibly unavailable in this environment).",
                    {"error": str(exc)[:240]},
                )
            )
    else:
        checks.append(
            _audit_check(
                "browser",
                "Browser Agent Probe",
                "info",
                "Skipped (enable include_browser_probe to run).",
            )
        )

    overall = _audit_overall_status(checks)
    pass_count = sum(1 for row in checks if row.get("status") == "pass")
    warn_count = sum(1 for row in checks if row.get("status") == "warn")
    fail_count = sum(1 for row in checks if row.get("status") == "fail")

    return {
        "overall_status": overall,
        "generated_at": now,
        "checks": checks,
        "summary": {
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
            "total": len(checks),
        },
        "metrics": log_store.get_metrics(),
        "active_runs": [run for run in orchestrator.list_runs(limit=50) if run.get("status") == "running"],
    }


def _n8n_templates() -> list[dict[str, Any]]:
    webhook_to_ollama = {
        "name": "Webhook -> Ollama -> Notify",
        "description": "Receive webhook data, summarize with local Ollama, then send a notification webhook.",
        "category": "automation",
        "workflow_json": {
            "name": "Webhook Ollama Notification",
            "nodes": [
                {
                    "id": "webhook-1",
                    "name": "Inbound Webhook",
                    "type": "n8n-nodes-base.webhook",
                    "position": [280, 280],
                    "parameters": {"path": "jimai-inbound", "httpMethod": "POST"},
                },
                {
                    "id": "http-1",
                    "name": "Call Ollama",
                    "type": "n8n-nodes-base.httpRequest",
                    "position": [560, 280],
                    "parameters": {
                        "url": "http://localhost:11434/api/chat",
                        "method": "POST",
                        "jsonParameters": True,
                        "options": {},
                    },
                },
                {
                    "id": "http-2",
                    "name": "Notify Webhook",
                    "type": "n8n-nodes-base.httpRequest",
                    "position": [860, 280],
                    "parameters": {
                        "url": "https://example.com/notify",
                        "method": "POST",
                        "jsonParameters": True,
                        "options": {},
                    },
                },
            ],
            "connections": {
                "Inbound Webhook": {"main": [[{"node": "Call Ollama", "type": "main", "index": 0}]]},
                "Call Ollama": {"main": [[{"node": "Notify Webhook", "type": "main", "index": 0}]]},
            },
            "active": False,
            "settings": {},
            "versionId": "jimai-template-1",
        },
    }
    repo_sync = {
        "name": "Repo Change Watcher",
        "description": "Poll git status and trigger downstream app/webhook actions when changes are detected.",
        "category": "devops",
        "workflow_json": {
            "name": "Repo Watch and Trigger",
            "nodes": [
                {
                    "id": "cron-1",
                    "name": "Every 5 Min",
                    "type": "n8n-nodes-base.cron",
                    "position": [260, 280],
                    "parameters": {"triggerTimes": {"item": [{"mode": "everyX", "value": 5, "unit": "minutes"}]}},
                },
                {
                    "id": "exec-1",
                    "name": "Git Status",
                    "type": "n8n-nodes-base.executeCommand",
                    "position": [520, 280],
                    "parameters": {"command": "git status --porcelain"},
                },
                {
                    "id": "if-1",
                    "name": "Has Changes?",
                    "type": "n8n-nodes-base.if",
                    "position": [760, 280],
                    "parameters": {"conditions": {"string": [{"value1": "={{$json[\"stdout\"]}}", "operation": "isNotEmpty"}]}},
                },
            ],
            "connections": {
                "Every 5 Min": {"main": [[{"node": "Git Status", "type": "main", "index": 0}]]},
                "Git Status": {"main": [[{"node": "Has Changes?", "type": "main", "index": 0}]]},
            },
            "active": False,
            "settings": {},
            "versionId": "jimai-template-2",
        },
    }
    return [webhook_to_ollama, repo_sync]


@router.get("/status")
async def status() -> dict[str, Any]:
    instances = await instance_lifecycle.status()
    n8n_status = await n8n_manager.status()
    workflow_status = workflow_store.status()
    free_stack_status = await free_stack_manager.status(include_probe=False)
    return {
        "power": power_manager.get_state(),
        "settings": settings_store.get(),
        "metrics": log_store.get_metrics(),
        "active_runs": [run for run in orchestrator.list_runs(limit=50) if run["status"] == "running"],
        "instances": instances,
        "automation_n8n": n8n_status,
        "automation_workflows": workflow_status,
        "free_stack": free_stack_status,
    }


@router.get("/admin/system-audit")
async def admin_system_audit(
    include_research_probe: bool = Query(default=False),
    include_browser_probe: bool = Query(default=False),
) -> dict[str, Any]:
    return await _run_system_audit(
        include_research_probe=include_research_probe,
        include_browser_probe=include_browser_probe,
    )


@router.get("/metrics")
async def metrics() -> dict[str, Any]:
    return log_store.get_metrics()


@router.get("/logs/actions")
async def action_logs(
    limit: int = Query(default=200, ge=1, le=2000),
    run_id: str | None = Query(default=None, description="When set, return the last N actions for this run only."),
) -> list[dict[str, Any]]:
    return log_store.list_action_logs(limit=limit, run_id=run_id)


@router.get("/power")
async def get_power() -> dict[str, Any]:
    return power_manager.get_state()


@router.post("/power")
async def set_power(req: PowerUpdateRequest) -> dict[str, Any]:
    return await power_manager.set_state(req.enabled, release_gpu_on_off=req.release_gpu_on_off)


@router.get("/settings")
async def get_settings() -> dict[str, Any]:
    return settings_store.get()


@router.post("/settings")
async def update_settings(req: SettingsUpdateRequest) -> dict[str, Any]:
    updates = req.dict(exclude_none=True)
    if "agent_models" in updates:
        raw = updates.get("agent_models")
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="agent_models must be a JSON object.")
        normalized: dict[str, str] = {}
        for key, value in raw.items():
            k = str(key or "").strip()
            v = str(value or "").strip()
            if not k:
                continue
            if not v:
                continue
            normalized[k] = v
        updates["agent_models"] = normalized
    if "continue_on_subagent_failure" in updates:
        updates["continue_on_subagent_failure"] = bool(updates.get("continue_on_subagent_failure"))
    if "auto_self_improve_on_failure_enabled" in updates:
        updates["auto_self_improve_on_failure_enabled"] = bool(updates.get("auto_self_improve_on_failure_enabled"))
    if "auto_self_improve_on_failure_include_stopped" in updates:
        updates["auto_self_improve_on_failure_include_stopped"] = bool(
            updates.get("auto_self_improve_on_failure_include_stopped")
        )
    if "auto_self_improve_on_failure_cooldown_seconds" in updates:
        updates["auto_self_improve_on_failure_cooldown_seconds"] = max(
            0,
            int(updates.get("auto_self_improve_on_failure_cooldown_seconds", 0)),
        )
    if "auto_self_improve_on_failure_max_per_day" in updates:
        updates["auto_self_improve_on_failure_max_per_day"] = max(
            0,
            int(updates.get("auto_self_improve_on_failure_max_per_day", 0)),
        )
    result = settings_store.update(updates)
    if updates:
        _append_settings_audit(updates)
    return result


@router.get("/settings/history")
async def get_settings_history(limit: int = Query(default=50, ge=1, le=500)) -> list[dict[str, Any]]:
    """Return the last N settings audit log entries."""
    if not _SETTINGS_AUDIT_FILE.exists():
        return []
    try:
        lines = _SETTINGS_AUDIT_FILE.read_text(encoding="utf-8").splitlines()
        entries: list[dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                logger.warning("Failed to parse audit log line as JSON", exc_info=True)
        return entries[-limit:]
    except Exception:
        logger.warning("Failed to read settings audit log", exc_info=True)
        return []


@router.post("/admin/reset-data")
async def admin_reset_data(req: ResetDataRequest) -> dict[str, Any]:
    await proactive_engine.stop()
    await browser_manager.close_all()
    runtime_reset = await orchestrator.reset_runtime_state()

    ensure_layout()
    removed: dict[str, int] = {}
    if req.clear_reviews:
        removed["reviews"] = _clear_dir(REVIEWS_DIR)
        if hasattr(review_store, "_cache"):
            review_store._cache = {}
    if req.clear_snapshots:
        removed["snapshots"] = _clear_dir(SNAPSHOTS_DIR)
        if hasattr(snapshot_store, "_cache"):
            snapshot_store._cache = {}
    if req.clear_logs:
        removed["logs"] = _clear_dir(LOGS_DIR)
        if hasattr(log_store, "_action_buffer"):
            log_store._action_buffer = []
        if hasattr(log_store, "_event_buffer"):
            log_store._event_buffer = []
        if hasattr(log_store, "_metrics_override"):
            log_store._metrics_override = dict(log_store.get_metrics())
            for key in list(log_store._metrics_override.keys()):
                log_store._metrics_override[key] = 0
            for key, value in {"runs_started": 0, "runs_completed": 0, "runs_failed": 0, "runs_stopped": 0}.items():
                log_store._metrics_override[key] = value
            _safe_write_json(LOGS_DIR / "metrics.json", log_store._metrics_override)
    if req.clear_memory:
        removed["memory"] = _clear_dir(MEMORY_DIR)
        if hasattr(memory_index_store, "_run_memory_override"):
            memory_index_store._run_memory_override = []
        _safe_write_json(MEMORY_DIR / "run_memory.json", [])
    if req.clear_index:
        removed["index"] = _clear_dir(INDEX_DIR)
        if hasattr(memory_index_store, "_code_index_override"):
            memory_index_store._code_index_override = None
    if req.clear_chats:
        removed["chats"] = _clear_dir(CHATS_DIR)
    if req.clear_runtime:
        removed["runtime"] = _clear_dir(RUNTIME_DIR)
    if req.clear_generated:
        removed["generated"] = _clear_dir(DATA_ROOT / "generated")
    if req.clear_self_improvement:
        removed["self_improvement"] = _clear_dir(DATA_ROOT / "self_improvement")
    if req.clear_proactive_goals:
        _safe_write_json(DATA_ROOT / "proactive_goals.json", [])
        removed["proactive_goals"] = 1
    if req.clear_teams:
        removed["teams"] = _clear_dir(TEAMS_DIR)
        if hasattr(team_store, "_cache"):
            team_store._cache = {}
    if req.clear_workflows:
        removed["workflows"] = _clear_dir(WORKFLOWS_DIR)
        if hasattr(workflow_store, "_cache"):
            workflow_store._cache = {}
    if req.clear_exports:
        removed["exports"] = _clear_dir(EXPORTS_DIR)
    if req.reset_settings:
        settings_store.update(dict(DEFAULT_SETTINGS))
        removed["settings"] = 1

    return {
        "ok": True,
        "removed": removed,
        "runtime_reset": runtime_reset,
    }


@router.post("/runs/start")
async def runs_start(req: RunStartRequest, _rl: None = Depends(check_run_rate_limit)) -> dict[str, Any]:
    try:
        return await orchestrator.start_run(req.dict(exclude_none=True))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs")
async def runs_list(
    status: str | None = Query(default=None, description="Filter by status: running, completed, failed, stopped, queued"),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    rows = orchestrator.list_runs(limit=limit + offset)
    if status is not None:
        rows = [r for r in rows if r.get("status") == status]
    return rows[offset : offset + limit]


@router.get("/runs/{run_id}")
async def runs_get(run_id: str) -> dict[str, Any]:
    run = orchestrator.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


@router.post("/runs/{run_id}/stop")
async def runs_stop(run_id: str, req: StopRunRequest) -> dict[str, Any]:
    try:
        return await orchestrator.request_stop(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/stop-all")
async def runs_stop_all() -> dict[str, Any]:
    """Stop all currently running runs."""
    running_ids = [
        run_id
        for run_id, run in orchestrator.runs.items()
        if run.get("status") == "running"
    ]
    stopped: list[str] = []
    for run_id in running_ids:
        try:
            await orchestrator.request_stop(run_id)
            stopped.append(run_id)
        except Exception:
            logger.warning("stop-all: failed to stop run %s", run_id, exc_info=True)
    return {"stopped": stopped, "count": len(stopped)}


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    if orchestrator.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return _stream(orchestrator.get_run_queue(run_id))


@router.get("/runs/{run_id}/messages")
async def run_messages(
    run_id: str,
    limit: int = Query(default=200, ge=1, le=2000),
    agent_id: str | None = None,
    channel: str | None = None,
) -> list[dict[str, Any]]:
    try:
        return orchestrator.list_run_messages(
            run_id,
            limit=limit,
            agent_id=agent_id,
            channel=channel,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/messages")
async def run_post_message(run_id: str, req: RunMessageRequest) -> dict[str, Any]:
    try:
        return await orchestrator.post_run_message(
            run_id,
            from_agent=req.from_agent,
            to_agent=req.to_agent,
            channel=req.channel,
            content=req.content,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/events")
async def global_events() -> StreamingResponse:
    return _stream(orchestrator.get_global_queue())


@router.get("/instances")
async def instances_status() -> dict[str, Any]:
    return await instance_lifecycle.status()


@router.post("/instances/register")
async def instances_register(req: InstanceRegisterRequest) -> dict[str, Any]:
    try:
        return await instance_lifecycle.register_instance(
            instance_id=req.instance_id,
            client=req.client,
            metadata=req.metadata,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/instances/heartbeat")
async def instances_heartbeat(req: InstanceHeartbeatRequest) -> dict[str, Any]:
    try:
        return await instance_lifecycle.heartbeat(
            instance_id=req.instance_id,
            client=req.client,
            metadata=req.metadata,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/instances/unregister")
async def instances_unregister(req: InstanceUnregisterRequest) -> dict[str, Any]:
    try:
        return await instance_lifecycle.unregister_instance(
            instance_id=req.instance_id,
            reason=req.reason,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/automation/n8n/status")
async def automation_n8n_status() -> dict[str, Any]:
    try:
        return await n8n_manager.status()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/automation/workflows/status")
async def automation_workflow_status() -> dict[str, Any]:
    return workflow_store.status()


@router.get("/automation/workflows/templates")
async def automation_workflow_templates() -> dict[str, Any]:
    return {"templates": workflow_store.templates()}


@router.get("/automation/workflows")
async def automation_workflow_list(limit: int = Query(default=200, ge=1, le=2000)) -> list[dict[str, Any]]:
    return workflow_store.list_workflows(limit=limit)


@router.get("/automation/workflows/{workflow_id}")
async def automation_workflow_get(workflow_id: str) -> dict[str, Any]:
    workflow = workflow_store.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return workflow


@router.post("/automation/workflows")
async def automation_workflow_upsert(req: WorkflowUpsertRequest) -> dict[str, Any]:
    graph = dict(req.graph or {})
    if not graph:
        raise HTTPException(status_code=400, detail="graph is required.")
    if not graph.get("name"):
        graph["name"] = req.name
    record = workflow_store.save_workflow(
        workflow_id=req.id,
        name=req.name,
        description=req.description,
        tags=req.tags,
        graph=graph,
        public_sources=req.public_sources,
    )
    return {"workflow": record}


@router.delete("/automation/workflows/{workflow_id}")
async def automation_workflow_delete(workflow_id: str) -> dict[str, bool]:
    return {"deleted": workflow_store.delete_workflow(workflow_id)}


@router.post("/automation/workflows/{workflow_id}/run")
async def automation_workflow_run(workflow_id: str, req: WorkflowRunRequest) -> dict[str, Any]:
    try:
        return await workflow_store.run_workflow(
            workflow_id,
            input_payload=req.input,
            max_steps=req.max_steps,
            continue_on_error=req.continue_on_error,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/automation/workflows/import/n8n")
async def automation_workflow_import_n8n(req: WorkflowImportN8nRequest) -> dict[str, Any]:
    graph = dict(req.workflow_json or {})
    if not graph:
        raise HTTPException(status_code=400, detail="workflow_json is required.")
    name = str(req.name or graph.get("name") or "Imported Workflow").strip() or "Imported Workflow"
    record = workflow_store.save_workflow(
        workflow_id=None,
        name=name,
        description=req.description or "Imported from n8n-compatible JSON.",
        tags=req.tags or ["n8n-import"],
        graph=graph,
        public_sources=workflow_store.public_sources(),
    )
    return {"workflow": record}


@router.post("/automation/n8n/start")
async def automation_n8n_start(req: N8nStartRequest) -> dict[str, Any]:
    try:
        return await n8n_manager.start(force=bool(req.force))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/automation/n8n/stop")
async def automation_n8n_stop() -> dict[str, Any]:
    try:
        return await n8n_manager.stop()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/automation/n8n/install")
async def automation_n8n_install(req: N8nInstallRequest) -> dict[str, Any]:
    try:
        return await n8n_manager.install_local(set_as_default=bool(req.set_as_default))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/automation/n8n/templates")
async def automation_n8n_templates() -> dict[str, Any]:
    return {"templates": _n8n_templates()}


@router.get("/integrations/free-stack/status")
async def free_stack_status(include_probe: bool = Query(default=True)) -> dict[str, Any]:
    try:
        return await free_stack_manager.status(include_probe=include_probe)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/integrations/free-stack/sync")
async def free_stack_sync_settings() -> dict[str, Any]:
    try:
        settings = free_stack_manager.sync_settings_from_env()
        status = await free_stack_manager.status(include_probe=False)
        return {"settings": settings, "status": status}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/integrations/free-stack/notify/test")
async def free_stack_notify_test(req: FreeStackNotifyRequest) -> dict[str, Any]:
    try:
        result = await free_stack_manager.send_phone_notification(
            title=req.title,
            message=req.message,
            priority=int(req.priority),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.get("ok") or result.get("skipped"):
        return result
    raise HTTPException(status_code=400, detail=str(result.get("error") or "Notification failed."))


@router.post("/oss/search")
async def open_source_search(req: OpenSourceSearchRequest) -> dict[str, Any]:
    return await search_open_source(
        req.query,
        limit=int(req.limit),
        min_stars=int(req.min_stars),
        language=req.language,
        include_unknown_license=bool(req.include_unknown_license),
    )


@router.get("/proactive/status")
async def proactive_status() -> dict[str, Any]:
    return proactive_engine.status()


@router.post("/proactive/start")
async def proactive_start() -> dict[str, Any]:
    return await proactive_engine.start()


@router.post("/proactive/stop")
async def proactive_stop() -> dict[str, Any]:
    return await proactive_engine.stop()


@router.post("/proactive/tick")
async def proactive_tick() -> dict[str, Any]:
    return await proactive_engine.tick()


@router.get("/proactive/goals")
async def proactive_goals(limit: int = Query(default=200, ge=1, le=2000)) -> list[dict[str, Any]]:
    return proactive_engine.list_goals(limit=limit)


@router.post("/proactive/goals")
async def proactive_goal_create(req: ProactiveGoalCreateRequest) -> dict[str, Any]:
    return proactive_engine.add_goal(
        name=req.name,
        objective=req.objective,
        interval_seconds=req.interval_seconds,
        enabled=req.enabled,
        run_template=req.run_template,
    )


@router.patch("/proactive/goals/{goal_id}")
async def proactive_goal_update(goal_id: str, req: ProactiveGoalUpdateRequest) -> dict[str, Any]:
    try:
        return proactive_engine.update_goal(goal_id, req.dict(exclude_none=True))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/proactive/goals/{goal_id}")
async def proactive_goal_delete(goal_id: str) -> dict[str, bool]:
    return {"deleted": proactive_engine.delete_goal(goal_id)}


@router.post("/self-improve/strengthen")
async def self_improve_strengthen(req: SelfImproveStrengthenRequest) -> dict[str, Any]:
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required.")
    return await _strengthen_self_improve_prompt(prompt)


@router.post("/self-improve/suggest-stream")
async def self_improve_suggest_stream(req: SelfImproveSuggestRequest, request: Request) -> StreamingResponse:
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required.")

    async def ndjson() -> AsyncGenerator[bytes, None]:
        try:
            async for row in _stream_self_improve_suggestions(prompt, req.max_suggestions, request):
                yield (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
        except asyncio.CancelledError:
            yield (json.dumps({"type": "stopped", "reason": "server_cancelled"}) + "\n").encode("utf-8")
            raise

    return StreamingResponse(ndjson(), media_type="application/x-ndjson")


@router.post("/self-improve/suggest")
async def self_improve_suggest(req: SelfImproveSuggestRequest) -> dict[str, Any]:
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required.")
    generated = await _generate_self_improve_suggestions(prompt, req.max_suggestions)
    rows = list(generated.get("suggestions") or [])
    return {
        "prompt": prompt,
        "model": generated.get("model"),
        "focus": generated.get("focus"),
        "requires_confirmation": True,
        "autonomous_notes": list(generated.get("autonomous_notes") or []),
        "suggestions": [
            {
                "id": f"suggestion-{idx + 1}",
                "text": str(text),
                "source": "autonomous",
            }
            for idx, text in enumerate(rows)
        ],
    }


@router.post("/self-improve/run")
async def self_improve_run(req: SelfImproveRunRequest) -> dict[str, Any]:
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required.")
    confirmed = _normalize_suggestion_texts(
        [str(item or "") for item in list(req.confirmed_suggestions or [])],
        max_items=20,
    )
    if req.direct_prompt_mode and not confirmed:
        confirmed = _normalize_suggestion_texts([prompt], max_items=20)
    if not confirmed:
        raise HTTPException(
            status_code=400,
            detail="Confirm at least one suggestion before starting self-improvement.",
        )
    try:
        run = await proactive_engine.run_self_improvement(
            prompt=prompt,
            confirmed_suggestions=confirmed,
        )
        return {
            **run,
            "prompt": prompt,
            "confirmed_suggestions": confirmed,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/assist/plan")
async def assist_plan(req: AssistBaseRequest) -> dict[str, Any]:
    """Return LLM-planned ephemeral agents for a question (no run started)."""
    settings = settings_store.get()
    model = str(settings.get("model", "qwen2.5-coder:14b"))
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="question is required.")
    surface = (req.surface or "general").strip() or "general"
    ctx = (req.context or "").strip()
    agents, delegate_objective = await _generate_assist_team(q, surface, ctx, model, req.max_agents)
    return {
        "model": model,
        "surface": surface,
        "agents": agents,
        "delegate_objective": delegate_objective,
    }


@router.post("/assist/analyze-stream")
async def assist_analyze_stream(req: AssistBaseRequest, request: Request) -> StreamingResponse:
    """Stream NDJSON: meta (planned agents), chunks (answer), done."""
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="question is required.")
    surface = (req.surface or "general").strip() or "general"
    ctx = (req.context or "").strip()
    max_agents = int(req.max_agents)

    async def ndjson() -> AsyncGenerator[bytes, None]:
        try:
            async for row in _stream_assist_analyze(q, surface, ctx, max_agents, request):
                yield (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
        except asyncio.CancelledError:
            yield (json.dumps({"type": "stopped", "reason": "server_cancelled"}) + "\n").encode("utf-8")
            raise

    return StreamingResponse(ndjson(), media_type="application/x-ndjson")


@router.post("/assist/spawn-run")
async def assist_spawn_run(req: AssistSpawnRunRequest, _rl: None = Depends(check_run_rate_limit)) -> dict[str, Any]:
    """Plan ephemeral agents and start an autonomous Agent Space run (same pipeline as Builder teams)."""
    settings = settings_store.get()
    model = str(settings.get("model", "qwen2.5-coder:14b"))
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="question is required.")
    surface = (req.surface or "general").strip() or "general"
    ctx = (req.context or "").strip()
    agents, delegate_objective = await _generate_assist_team(q, surface, ctx, model, req.max_agents)
    agents_augmented, used_saved_teams, used_agent_packs = _augment_builder_team(
        agents,
        prompt=q,
        context=ctx,
        use_saved_teams=True,
        auto_agent_packs=True,
        max_agents=10,
    )
    objective_core = f"[assist:{surface}] {q}"
    if ctx:
        objective_core += f"\n\nContext:\n{ctx}"
    objective_core = objective_core[:8000]
    team_agents, workflow_meta = orchestrator._normalize_subagents(
        subagents=agents_augmented,
        objective=objective_core,
        required_checks=list(settings.get("required_checks") or []) if isinstance(settings.get("required_checks"), list) else [],
        payload_actions=[],
    )
    full_objective = f"{objective_core}\n\nDelegate: {delegate_objective}"[:10000]
    ma = int(settings.get("max_actions", 40))
    ms = int(settings.get("max_seconds", 1200))
    payload: dict[str, Any] = {
        "objective": full_objective,
        "autonomous": bool(req.autonomous),
        "review_gate": bool(settings.get("review_gate", True)),
        "allow_shell": bool(settings.get("allow_shell", False)),
        "command_profile": str(settings.get("command_profile", "safe")),
        "max_actions": max(12, min(ma, 48)),
        "max_seconds": max(300, min(ms, 3600)),
        "team": {
            "name": f"Assist · {surface}",
            "description": "Ephemeral team created by cross-surface assist.",
            "agents": team_agents,
            "save": False,
            "metadata": {"source": "assist.spawn-run", "surface": surface, "model": model},
        },
        "subagent_retry_attempts": max(0, int(settings.get("subagent_retry_attempts", 2))),
        "continue_on_subagent_failure": bool(settings.get("continue_on_subagent_failure", True)),
        "review_scope": "workspace",
    }
    if bool(settings.get("run_auto_force_research_enabled", False)):
        payload["force_research"] = True
    try:
        run = await orchestrator.start_run(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "run": run,
        "surface": surface,
        "model": model,
        "delegate_objective": delegate_objective,
        "used_saved_teams": used_saved_teams,
        "used_agent_packs": used_agent_packs,
        "complexity": workflow_meta.get("complexity", {}),
        "planned_agent_count": len(agents),
        "team_agent_count": len(team_agents),
    }


@router.post("/builder/clarify")
async def builder_clarify(req: BuilderClarifyRequest) -> dict[str, Any]:
    settings = settings_store.get()
    model = str(settings.get("model", "qwen2.5-coder:14b"))
    max_q = max(1, int(req.max_questions))
    prompt = (
        "You are an app-scoping assistant. Generate clarification questions before implementation starts.\n"
        "Return strict JSON with keys: questions (string[]), assumptions (string[]), draft_objective (string).\n"
        f"Limit questions to at most {max_q} and focus on missing decisions that block build quality.\n\n"
        f"User request:\n{req.prompt.strip()}\n\n"
        f"Extra context:\n{req.context.strip()}\n"
    )
    questions: list[str] = []
    assumptions: list[str] = []
    draft_objective = _build_launch_objective(req.prompt, req.context, {})
    try:
        text = await ollama_client.chat_full(
            model=model,
            messages=[
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        parsed = _safe_parse_json_object(text) or {}
        raw_questions = parsed.get("questions") if isinstance(parsed, dict) else []
        raw_assumptions = parsed.get("assumptions") if isinstance(parsed, dict) else []
        if isinstance(raw_questions, list):
            for item in raw_questions:
                q = str(item or "").strip()
                if q:
                    questions.append(q)
        if isinstance(raw_assumptions, list):
            for item in raw_assumptions:
                a = str(item or "").strip()
                if a:
                    assumptions.append(a)
        parsed_objective = str((parsed.get("draft_objective") if isinstance(parsed, dict) else "") or "").strip()
        if parsed_objective:
            draft_objective = parsed_objective
    except Exception:
        questions = []
        assumptions = []

    if not questions:
        questions = _fallback_builder_questions(req.prompt, max_q)
    questions = questions[:max_q]
    assumptions = assumptions[:8]

    return {
        "questions": questions,
        "assumptions": assumptions,
        "draft_objective": draft_objective,
        "needs_clarification": len(questions) > 0,
        "model": model,
    }


@router.post("/builder/launch")
async def builder_launch(req: BuilderLaunchRequest) -> dict[str, Any]:
    settings = settings_store.get()
    model = str(settings.get("model", "qwen2.5-coder:14b"))
    objective = _build_launch_objective(req.prompt, req.context, req.answers)
    open_source_refs: list[dict[str, Any]] = []
    if bool(settings.get("builder_open_source_lookup_enabled", True)):
        try:
            max_repos = max(1, min(8, int(settings.get("builder_open_source_max_repos", 3))))
            oss = await search_open_source(
                req.prompt,
                limit=max_repos,
                min_stars=30,
                language="",
                include_unknown_license=False,
            )
            open_source_refs = [row for row in list(oss.get("results") or []) if isinstance(row, dict)]
            if open_source_refs:
                lines = ["", "Open-source reference candidates (free/open-source licensed):"]
                for row in open_source_refs[:max_repos]:
                    name = str(row.get("full_name") or row.get("name") or "").strip()
                    url = str(row.get("url") or "").strip()
                    stars = int(row.get("stars") or 0)
                    desc = str(row.get("description") or "").strip()
                    if name and url:
                        lines.append(f"- {name} ({stars} stars): {url}")
                        if desc:
                            lines.append(f"  purpose: {desc[:180]}")
                objective = f"{objective}\n" + "\n".join(lines).strip()
        except Exception:
            open_source_refs = []

    team_name = str(req.team_name or "Auto Build Team").strip() or "Auto Build Team"
    team_agents = _fallback_builder_team()
    used_saved_teams: list[str] = []
    used_agent_packs: list[str] = []

    # Try generating a better team blueprint from local Ollama; fall back safely.
    try:
        team_prompt = (
            "Design a compact subagent team for building a full app from request + answers.\n"
            "Return strict JSON with key agents: [{id,role,depends_on,description,actions?}].\n"
            "Use dependency order and keep 3-6 agents.\n\n"
            f"Request:\n{req.prompt.strip()}\n\n"
            f"Context:\n{req.context.strip()}\n\n"
            f"Answers:\n{json.dumps(req.answers, ensure_ascii=False)}\n"
        )
        team_text = await ollama_client.chat_full(
            model=model,
            messages=[
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": team_prompt},
            ],
            temperature=0.2,
        )
        parsed_team = _safe_parse_json_object(team_text) or {}
        raw_agents = parsed_team.get("agents") if isinstance(parsed_team, dict) else None
        if isinstance(raw_agents, list):
            candidate: list[dict[str, Any]] = []
            for row in raw_agents[:6]:
                if not isinstance(row, dict):
                    continue
                agent_id = str(row.get("id") or "").strip()
                if not agent_id:
                    continue
                candidate.append(
                    {
                        "id": agent_id,
                        "role": str(row.get("role") or "coder"),
                        "depends_on": [str(dep) for dep in list(row.get("depends_on") or []) if str(dep).strip()],
                        "description": str(row.get("description") or ""),
                        "actions": list(row.get("actions") or []),
                        "model": str(row.get("model") or "").strip(),
                    }
                )
            if candidate:
                team_agents = candidate
    except Exception:
        logger.warning("Builder launch: failed to generate or parse team agents from LLM response", exc_info=True)

    team_agents, used_saved_teams, used_agent_packs = _augment_builder_team(
        team_agents,
        prompt=req.prompt,
        context=req.context,
        use_saved_teams=bool(req.use_saved_teams),
        auto_agent_packs=bool(req.auto_agent_packs),
        max_agents=12,
    )
    team_agents, workflow_meta = orchestrator._normalize_subagents(
        subagents=team_agents,
        objective=objective,
        required_checks=list(req.required_checks or []),
        payload_actions=[],
    )

    payload: dict[str, Any] = {
        "objective": objective,
        "autonomous": bool(req.autonomous),
        "review_gate": bool(req.review_gate),
        "allow_shell": bool(req.allow_shell),
        "command_profile": str(req.command_profile or "safe"),
        "required_checks": list(req.required_checks or []),
        "team": {
            "name": team_name,
            "description": "Auto-generated builder team",
            "agents": team_agents,
            "save": bool(req.save_team),
            "metadata": {"source": "builder.launch"},
        },
    }
    if req.force_research is not None:
        payload["force_research"] = bool(req.force_research)

    if bool(req.autonomous) and bool(settings.get("overnight_autonomy_enabled", True)):
        overnight_hours = max(1, int(settings.get("overnight_max_hours", 10)))
        overnight_actions = max(40, int(settings.get("overnight_max_actions", 320)))
        default_max_seconds = max(int(settings.get("max_seconds", 1200)), overnight_hours * 3600)
        default_max_actions = max(int(settings.get("max_actions", 40)), overnight_actions)
        payload["max_seconds"] = int(req.max_seconds) if req.max_seconds is not None else default_max_seconds
        payload["max_actions"] = int(req.max_actions) if req.max_actions is not None else default_max_actions
    else:
        if req.max_actions is not None:
            payload["max_actions"] = int(req.max_actions)
        if req.max_seconds is not None:
            payload["max_seconds"] = int(req.max_seconds)

    if req.create_git_checkpoint is not None:
        payload["create_git_checkpoint"] = bool(req.create_git_checkpoint)
    payload["subagent_retry_attempts"] = max(
        0,
        int(
            req.subagent_retry_attempts
            if req.subagent_retry_attempts is not None
            else settings.get("subagent_retry_attempts", 2)
        ),
    )
    payload["continue_on_subagent_failure"] = bool(
        req.continue_on_subagent_failure
        if req.continue_on_subagent_failure is not None
        else settings.get("continue_on_subagent_failure", True)
    )
    payload["review_scope"] = "workspace"

    try:
        run = await orchestrator.start_run(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "run": run,
        "team_name": team_name,
        "team_agent_count": len(team_agents),
        "objective": objective,
        "open_source_refs": open_source_refs,
        "used_saved_teams": used_saved_teams,
        "used_agent_packs": used_agent_packs,
        "complexity": workflow_meta.get("complexity", {}),
    }


@router.post("/builder/preview")
async def builder_preview(req: BuilderPreviewRequest) -> dict[str, Any]:
    settings = settings_store.get()
    model = str(settings.get("model", "qwen2.5-coder:14b"))
    base_agents = _fallback_builder_team()
    team_agents, used_saved_teams, used_agent_packs = _augment_builder_team(
        base_agents,
        prompt=req.prompt,
        context=req.context,
        use_saved_teams=bool(req.use_saved_teams),
        auto_agent_packs=bool(req.auto_agent_packs),
        max_agents=12,
    )
    preview_objective = _build_launch_objective(req.prompt, req.context, {})
    team_agents, workflow_meta = orchestrator._normalize_subagents(
        subagents=team_agents,
        objective=preview_objective,
        required_checks=[],
        payload_actions=[],
    )
    return {
        "model": model,
        "team_name": str(req.team_name or "Auto Build Team").strip() or "Auto Build Team",
        "base_agent_count": len(base_agents),
        "team_agent_count": len(team_agents),
        "used_saved_teams": used_saved_teams,
        "used_agent_packs": used_agent_packs,
        "team_agents": [
            {
                "id": str(agent.get("id", "")),
                "role": str(agent.get("role", "coder")),
                "worker_level": int(agent.get("worker_level") or 1),
                "model": str(agent.get("model", "")),
                "depends_on": [str(dep) for dep in list(agent.get("depends_on") or []) if str(dep).strip()],
                "description": str(agent.get("description", "")),
            }
            for agent in team_agents
        ],
        "complexity": workflow_meta.get("complexity", {}),
        "option_help": {
            "save_team": "Stores this generated team template for future runs.",
            "review_gate": "Keeps changes in review diffs before apply.",
            "allow_shell": "Allows shell commands under selected profile constraints.",
            "command_profile": "safe=restrictive, dev=balanced, unrestricted=maximum access.",
            "auto_agent_packs": "Adds specialist agents based on prompt scope.",
            "use_saved_teams": "Reuses matching local team templates automatically.",
        },
    }


@router.get("/skills")
async def list_skills(limit: int = Query(default=200, ge=1, le=2000)) -> list[dict[str, Any]]:
    return skill_store.list_skills(limit=limit)


@router.post("/skills")
async def upsert_skill(req: SkillUpsertRequest) -> dict[str, Any]:
    return skill_store.upsert_skill(
        name=req.name,
        description=req.description,
        content=req.content,
        tags=req.tags,
        complexity=req.complexity,
        source=req.source,
        metadata=req.metadata,
        slug=req.slug.strip() if isinstance(req.slug, str) and req.slug.strip() else None,
    )


@router.post("/skills/install-defaults")
async def install_default_skills() -> dict[str, Any]:
    installed = skill_store.install_default_skills()
    return {"installed_count": len(installed), "installed": installed}


@router.post("/skills/auto-add")
async def auto_add_skills(req: SkillAutoAddRequest) -> dict[str, Any]:
    created = await skill_store.auto_add_for_objective(req.objective, limit=req.max_new_skills)
    selected = skill_store.select_for_objective(req.objective, limit=8)
    selected_summary = [
        {
            "slug": str(row.get("slug", "")),
            "name": str(row.get("name", "")),
            "description": str(row.get("description", "")),
            "tags": [str(tag) for tag in list(row.get("tags") or []) if str(tag).strip()],
            "complexity": int(row.get("complexity") or 1),
            "source": str(row.get("source", "custom")),
            "match_score": float(row.get("match_score") or 0.0),
        }
        for row in selected
    ]
    return {
        "created_count": len(created),
        "created": created,
        "selected": selected_summary,
    }


@router.post("/skills/select")
async def select_skills(req: SkillSelectRequest) -> dict[str, Any]:
    selected = skill_store.select_for_objective(req.objective, limit=req.limit)
    context = skill_store.build_context(selected, max_chars=12000) if req.include_context else ""
    selected_summary = [
        {
            "slug": str(row.get("slug", "")),
            "name": str(row.get("name", "")),
            "description": str(row.get("description", "")),
            "tags": [str(tag) for tag in list(row.get("tags") or []) if str(tag).strip()],
            "complexity": int(row.get("complexity") or 1),
            "source": str(row.get("source", "custom")),
            "match_score": float(row.get("match_score") or 0.0),
        }
        for row in selected
    ]
    return {
        "selected_count": len(selected),
        "selected": selected_summary,
        "context": context,
    }


@router.get("/skills/{skill_name}")
async def get_skill(skill_name: str) -> dict[str, Any]:
    skill = skill_store.get_skill(skill_name)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found.")
    return skill


@router.delete("/skills/{skill_name}")
async def delete_skill(skill_name: str) -> dict[str, bool]:
    return {"deleted": skill_store.delete_skill(skill_name)}


@router.get("/teams")
async def list_teams(limit: int = Query(default=200, ge=1, le=2000)) -> list[dict[str, Any]]:
    return team_store.list_teams(limit=limit)


@router.post("/teams")
async def upsert_team(req: TeamUpsertRequest) -> dict[str, Any]:
    if not req.agents:
        raise HTTPException(status_code=400, detail="agents is required.")
    return team_store.save_team(
        team_id=req.id,
        name=req.name,
        description=req.description,
        agents=[agent.dict(exclude_none=True) for agent in req.agents],
        metadata=req.metadata,
    )


@router.get("/teams/{team_id}")
async def get_team(team_id: str) -> dict[str, Any]:
    team = team_store.get_team(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found.")
    return team


@router.delete("/teams/{team_id}")
async def delete_team(team_id: str) -> dict[str, bool]:
    return {"deleted": team_store.delete_team(team_id)}


@router.get("/teams/{team_id}/messages")
async def list_team_messages(
    team_id: str,
    limit: int = Query(default=200, ge=1, le=2000),
    run_id: str | None = None,
    channel: str | None = None,
) -> list[dict[str, Any]]:
    try:
        return team_store.list_messages(
            team_id,
            limit=limit,
            run_id=run_id,
            channel=channel,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/teams/{team_id}/messages")
async def post_team_message(team_id: str, req: TeamMessageRequest) -> dict[str, Any]:
    try:
        return team_store.append_message(
            team_id,
            run_id=req.run_id,
            from_agent=req.from_agent,
            to_agent=req.to_agent,
            channel=req.channel,
            content=req.content,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/reviews")
async def list_reviews(limit: int = Query(default=200, ge=1, le=2000)) -> list[dict[str, Any]]:
    return review_store.list_reviews(limit=limit)


@router.get("/reviews/{review_id}")
async def get_review(review_id: str) -> dict[str, Any]:
    review = review_store.get_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found.")
    return review


@router.post("/reviews/{review_id}/approve")
async def approve_review(review_id: str) -> dict[str, Any]:
    try:
        return review_store.approve(review_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/reviews/{review_id}/reject")
async def reject_review(review_id: str, req: RejectRequest) -> dict[str, Any]:
    try:
        return review_store.reject(review_id, reason=req.reason)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/reviews/{review_id}/apply")
async def apply_review(review_id: str) -> dict[str, Any]:
    cfg = settings_store.get()
    try:
        review = review_store.apply(
            review_id,
            snapshot_store=snapshot_store,
            create_git_checkpoint=bool(cfg.get("create_git_checkpoint", False)),
        )
        log_store.increment("reviews_applied", 1)
        return review
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reviews/{review_id}/undo")
async def undo_review(review_id: str) -> dict[str, Any]:
    review = review_store.get_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found.")
    snapshot_id = str(review.get("snapshot_id") or "").strip()
    if not snapshot_id:
        raise HTTPException(status_code=400, detail="Review has no snapshot to undo.")
    try:
        rollback_result = snapshot_store.restore_snapshot(snapshot_id)
        review = review_store.mark_undone(review_id, reason="Undo requested from review workflow.")
        log_store.increment("rollbacks", 1)
        return {"review": review, **rollback_result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reviews/{review_id}/commit")
async def commit_review(review_id: str, req: ReviewCommitRequest) -> dict[str, Any]:
    cfg = settings_store.get()
    review = review_store.get_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found.")

    status = str(review.get("status") or "pending")
    try:
        if req.auto_apply and status in {"pending", "approved"}:
            if status == "pending":
                review_store.approve(review_id)
            review = review_store.apply(
                review_id,
                snapshot_store=snapshot_store,
                create_git_checkpoint=bool(cfg.get("create_git_checkpoint", False)),
            )
            log_store.increment("reviews_applied", 1)
        else:
            review = review_store.get_review(review_id) or review
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to auto-apply review: {exc}") from exc

    if str(review.get("status") or "") != "applied":
        raise HTTPException(
            status_code=400,
            detail="Review must be applied before commit. Use auto_apply=true or apply manually first.",
        )

    changed_paths = [
        str(change.get("path") or "").replace("\\", "/")
        for change in list(review.get("changes") or [])
        if str(change.get("path") or "").strip()
    ]
    try:
        commit_info = _commit_review_paths(changed_paths, req.message)
        log_store.increment("git_commits", 1)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "review_id": review_id,
        "review_status": review.get("status"),
        "snapshot_id": review.get("snapshot_id"),
        **commit_info,
    }


@router.post("/rollback/{snapshot_id}")
async def rollback(snapshot_id: str) -> dict[str, Any]:
    try:
        result = snapshot_store.restore_snapshot(snapshot_id)
        log_store.increment("rollbacks", 1)
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/snapshots")
async def list_snapshots(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    return snapshot_store.list_snapshots(limit=limit)


@router.post("/index/rebuild")
async def rebuild_index() -> dict[str, Any]:
    return memory_index_store.rebuild_code_index()


@router.get("/index/search")
async def search_index(q: str = Query(..., min_length=1), limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
    return {"query": q, "results": memory_index_store.search_code_index(q, limit=limit)}


@router.get("/memory/recent")
async def memory_recent(limit: int = Query(default=30, ge=1, le=200)) -> list[dict[str, Any]]:
    return memory_index_store.list_recent_runs(limit=limit)


@router.post("/export")
async def export_module(req: ExportRequest) -> dict[str, Any]:
    if not req.include_paths:
        raise HTTPException(status_code=400, detail="include_paths is required.")
    return export_items(req.target_folder, req.include_paths, label=req.label)


def _search_text_in_repo(query: str, directory: Path, max_results: int) -> list[dict[str, Any]]:
    """Line-level substring search; same ignore rules as code index."""
    needle = (query or "").strip()
    if not needle:
        return []
    root_resolved = PROJECT_ROOT.resolve()
    matches: list[dict[str, Any]] = []
    try:
        dir_resolved = directory.resolve()
    except Exception:
        return []
    if not str(dir_resolved).startswith(str(root_resolved)):
        return []
    for path in dir_resolved.rglob("*"):
        if len(matches) >= max_results:
            break
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(root_resolved)
        except ValueError:
            continue
        if any(part in IGNORED_DIR_NAMES for part in rel.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        lines = text.splitlines()
        for line_no, line in enumerate(lines, start=1):
            if len(matches) >= max_results:
                break
            if needle in line:
                matches.append(
                    {
                        "path": rel.as_posix(),
                        "line": line_no,
                        "preview": line.strip()[:280],
                    }
                )
    return matches


@router.post("/workspace/search-text")
async def workspace_search_text(req: WorkspaceTextSearchRequest) -> dict[str, Any]:
    rel, abs_path = _resolve_repo_path((req.path_prefix or ".").strip() or ".")
    if not abs_path.is_dir():
        raise HTTPException(status_code=400, detail="path_prefix must be a directory inside the repository.")
    matches = _search_text_in_repo(req.query.strip(), abs_path, req.max_results)
    return {"query": req.query.strip(), "path_prefix": rel or ".", "matches": matches, "count": len(matches)}


@router.get("/tools/tree")
async def tools_tree(
    path: str = Query(default=".", min_length=1),
    depth: int = Query(default=8, ge=1, le=32),
    limit: int = Query(default=10000, ge=100, le=120000),
    include_hidden: bool = Query(default=False),
) -> dict[str, Any]:
    rel, abs_path = _resolve_repo_path(path)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="Path not found.")
    if abs_path.is_file():
        return {
            "root": rel or ".",
            "depth": depth,
            "limit": limit,
            "scanned": 1,
            "truncated": False,
            "tree": {
                "name": abs_path.name,
                "path": rel or ".",
                "type": "file",
            },
        }
    return _build_repo_tree(
        root_abs=abs_path,
        root_rel=rel,
        depth=depth,
        limit=limit,
        include_hidden=include_hidden,
    )


@router.post("/tools/read")
async def tools_read(req: ToolReadRequest) -> dict[str, Any]:
    rel, abs_path = _resolve_repo_path(req.path)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    return {"path": rel, "content": abs_path.read_text(encoding="utf-8", errors="replace")}


@router.post("/tools/write")
async def tools_write(req: ToolWriteRequest) -> dict[str, Any]:
    rel, abs_path = _resolve_repo_path(req.path)
    old_content = abs_path.read_text(encoding="utf-8", errors="replace") if abs_path.exists() else ""
    existed = abs_path.exists()
    change = {
        "path": rel,
        "old_content": old_content,
        "new_content": req.content,
        "existed_before": existed,
        "reason": "manual_tool_write",
    }
    if req.review_gate:
        review = review_store.create_review(
            run_id="manual",
            objective=f"Manual write {rel}",
            changes=[change],
            metadata={"source": "tools.write", "review_scope": "workspace"},
        )
        log_store.increment("reviews_created", 1)
        return {"mode": "review", "review": review}
    snapshot = snapshot_store.create_snapshot(run_id="manual", note=f"Manual direct write {rel}", files=[change])
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(req.content, encoding="utf-8")
    return {"mode": "direct", "snapshot_id": snapshot["id"], "path": rel}


@router.post("/tools/replace")
async def tools_replace(req: ToolReplaceRequest) -> dict[str, Any]:
    rel, abs_path = _resolve_repo_path(req.path)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    old_content = abs_path.read_text(encoding="utf-8", errors="replace")
    if not req.find:
        raise HTTPException(status_code=400, detail="find cannot be empty.")
    new_content = old_content.replace(req.find, req.replace, req.count if req.count > 0 else -1)
    if new_content == old_content:
        raise HTTPException(status_code=400, detail="No replacements made.")
    change = {
        "path": rel,
        "old_content": old_content,
        "new_content": new_content,
        "existed_before": True,
        "reason": "manual_tool_replace",
    }
    if req.review_gate:
        review = review_store.create_review(
            run_id="manual",
            objective=f"Manual replace in {rel}",
            changes=[change],
            metadata={"source": "tools.replace", "review_scope": "workspace"},
        )
        log_store.increment("reviews_created", 1)
        return {"mode": "review", "review": review}
    snapshot = snapshot_store.create_snapshot(run_id="manual", note=f"Manual direct replace {rel}", files=[change])
    abs_path.write_text(new_content, encoding="utf-8")
    return {"mode": "direct", "snapshot_id": snapshot["id"], "path": rel}


@router.post("/tools/shell")
async def tools_shell(req: ToolShellRequest) -> dict[str, Any]:
    cfg = settings_store.get()
    profile = req.profile or str(cfg.get("command_profile", "safe"))
    allow_shell = bool(cfg.get("allow_shell", True))
    cwd = req.cwd
    base = (PROJECT_ROOT / cwd).resolve() if not Path(cwd).is_absolute() else Path(cwd).resolve()
    if not str(base).startswith(str(PROJECT_ROOT.resolve())):
        raise HTTPException(status_code=400, detail="cwd is outside repository.")
    try:
        result = await run_command(
            command=req.command,
            cwd=str(base),
            profile=profile,
            repo_root=PROJECT_ROOT,
            allow_shell=allow_shell,
            timeout=req.timeout,
        )
    except PolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result
