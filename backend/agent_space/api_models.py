"""Pydantic request models for the Agent Space API router.

Extracted verbatim from ``api.py`` so the router module stays focused on route
handlers and helper logic. No behavioural change — these are the same schemas,
imported back into ``api.py``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


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


class SelfImproveKnowledgeRequest(BaseModel):
    knowledge: str = Field(default="", max_length=20000)


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
    ollama_model: str | None = None
    builder_model_mode: str = "manual"


class BuilderPreviewRequest(BaseModel):
    prompt: str = Field(min_length=1)
    context: str = ""
    team_name: str = "Auto Build Team"
    auto_agent_packs: bool = True
    use_saved_teams: bool = True
    ollama_model: str | None = None
    builder_model_mode: str = "manual"
