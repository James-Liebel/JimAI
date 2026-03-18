"""Singleton runtime objects for Agent Space."""

import logging

from .chat_store import AgentSpaceChatStore

logger = logging.getLogger(__name__)
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


async def shutdown() -> None:
    await proactive_engine.stop()
    await n8n_manager.shutdown()
    await instance_lifecycle.shutdown()
    await browser_manager.close_all()
