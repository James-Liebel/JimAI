"""Singleton runtime objects for Agent Space."""

import logging
from typing import Any

from .chat_store import AgentSpaceChatStore

logger = logging.getLogger(__name__)
from .autonomy import runtime as autonomy_runtime
from .browser_agent import BrowserAgentManager
from .automation_runtime import N8nRuntimeManager
from .config import SettingsStore
from .instance_lifecycle import InstanceLifecycleManager
from .log_store import LogStore
from .memory_index import MemoryIndexStore
from .orchestrator import AgentSpaceOrchestrator
from .power import PowerManager
from .free_stack import FreeStackIntegrationManager
from .proactive import ProactiveEngine
from .review_store import ReviewStore
from .snapshot_store import SnapshotStore
from .skill_store import SkillStore
from .team_store import TeamStore
from .workflow_engine import WorkflowStore

settings_store = SettingsStore()
log_store = LogStore()
review_store = ReviewStore()
snapshot_store = SnapshotStore()
memory_index_store = MemoryIndexStore()
power_manager = PowerManager()
chat_store = AgentSpaceChatStore()
team_store = TeamStore()
skill_store = SkillStore(settings_store=settings_store)
browser_manager = BrowserAgentManager()
instance_lifecycle = InstanceLifecycleManager()
n8n_manager = N8nRuntimeManager(settings_store=settings_store)
workflow_store = WorkflowStore(settings_store=settings_store)
free_stack_manager = FreeStackIntegrationManager(settings_store=settings_store)

orchestrator = AgentSpaceOrchestrator(
    settings=settings_store,
    logs=log_store,
    reviews=review_store,
    snapshots=snapshot_store,
    memory_index=memory_index_store,
    power=power_manager,
    chat_store=chat_store,
    team_store=team_store,
    skill_store=skill_store,
    browser_manager=browser_manager,
    free_stack_manager=free_stack_manager,
)

proactive_engine = ProactiveEngine(
    orchestrator=orchestrator,
    power=power_manager,
    logs=log_store,
)
orchestrator.add_run_complete_hook(proactive_engine.handle_run_completion)


# ----- Autonomy wiring ----------------------------------------------------
# Record every completed run as an episodic memory entry, capture verifier-
# approved output as a skill, and bind the heartbeat scheduler.

async def _autonomy_record_completion(
    run: dict[str, Any],
    payload: dict[str, Any],
    completion_summary: dict[str, Any],
) -> dict[str, Any] | None:
    try:
        memory = autonomy_runtime.get_episodic_memory()
        outcome = str(run.get("status") or "unknown")
        objective = str(run.get("objective") or "")
        summary_text = str(completion_summary.get("text") or objective)[:1800]
        await memory.record(
            run_id=str(run.get("id") or ""),
            agent_id="orchestrator",
            event="run_completed",
            outcome=outcome,
            summary=summary_text,
            metadata={
                "review_count": len(run.get("review_ids") or []),
                "snapshot_count": len(run.get("snapshot_ids") or []),
                "action_count": run.get("action_count", 0),
                "team_id": run.get("team_id"),
                "skills": list(run.get("skills") or []),
            },
        )

        if outcome.lower() in {"completed", "success", "succeeded"} and objective:
            library = autonomy_runtime.get_skill_library()
            artifact_lines = [
                f"objective: {objective[:400]}",
                f"action_count: {run.get('action_count', 0)}",
                f"summary: {summary_text}",
            ]
            await library.capture(
                name=f"run-{str(run.get('id'))[:8]}",
                description=f"Verified pattern from {outcome} run.",
                objective=objective,
                artifact="\n".join(artifact_lines),
                artifact_type="trace",
                tags=[t for t in (run.get("skills") or []) if isinstance(t, str)],
                verifier_score=1.0,
                metadata={
                    "run_id": run.get("id"),
                    "team_id": run.get("team_id"),
                },
            )
    except Exception as exc:
        logger.debug("autonomy completion hook error: %s", exc)
    return None


orchestrator.add_run_complete_hook(_autonomy_record_completion)


# ----- Security wiring ----------------------------------------------------
# Pre-action hook: route every tool call through ToolGate, then check
# outbound URLs against the EgressGuardian for browser/web tools.

from .security import runtime as security_runtime
from .security.tool_gate import ToolGateError


async def _security_pre_action(run_id: str, agent_id: str, action: dict[str, Any]) -> None:
    action_type = str(action.get("type") or "").strip()
    if not action_type:
        return
    args = {k: v for k, v in (action or {}).items() if k != "type"}

    # 1) ToolGate policy check (capability + arg shape + secret scan).
    try:
        await security_runtime.get_tool_gate().check(
            agent_id=agent_id, tool=action_type, args=args
        )
    except ToolGateError as exc:
        raise RuntimeError(f"tool_gate denied: {exc}") from exc

    # 2) Egress allowlist for outbound network actions.
    if action_type in {"web_fetch", "browser_open", "browser_navigate"}:
        url = str(action.get("url") or "").strip()
        if url:
            verdict = security_runtime.get_egress_guardian().check_url(url)
            if not verdict.allowed:
                raise RuntimeError(f"egress_guardian denied: {verdict.reason}")


orchestrator.add_pre_action_hook(_security_pre_action)


async def _heartbeat_action(job: Any) -> dict[str, Any] | None:
    """Heartbeat fires -> start a run from the job's objective."""
    payload = dict(job.payload or {})
    payload.setdefault("objective", job.objective)
    payload.setdefault("autonomous", True)
    payload.setdefault("review_gate", True)
    if not power_manager.is_enabled():
        return {"status": "power_off", "id": ""}
    try:
        run = await orchestrator.start_run(payload)
        return {"id": run.get("id"), "status": run.get("status"), "run_id": run.get("id")}
    except Exception as exc:
        logger.warning("heartbeat job %s failed to start run: %s", job.id, exc)
        raise


heartbeat_scheduler = autonomy_runtime.bind_heartbeat(_heartbeat_action)


async def startup() -> None:
    await instance_lifecycle.startup()
    # Research memory cache bootstrap (Qdrant collection + embedding dimension).
    try:
        from .web_research import warm_research_memory_collection

        await warm_research_memory_collection()
    except Exception:
        logger.warning("Failed to warm research memory collection on startup", exc_info=True)
    cfg = settings_store.get()
    engine = str(cfg.get("automation_engine", "open-source")).strip().lower()
    if engine in {"n8n", "hybrid"}:
        await n8n_manager.startup()
    if bool(cfg.get("proactive_enabled", False)):
        await proactive_engine.start()
    if bool(cfg.get("heartbeat_enabled", False)):
        try:
            await heartbeat_scheduler.start()
        except Exception as exc:
            logger.warning("Failed to start heartbeat scheduler: %s", exc)


async def shutdown() -> None:
    await proactive_engine.stop()
    await autonomy_runtime.shutdown()
    await n8n_manager.shutdown()
    await instance_lifecycle.shutdown()
    await browser_manager.close_all()
