"""Lazy singletons for the autonomy primitives.

Wires the four primitives together with a single ``initialize()`` entrypoint
that the rest of the platform can call without worrying about construction
order. Exposes a small surface for the orchestrator and API layer:

    get_episodic_memory()   -> EpisodicMemory
    get_skill_library()     -> SkillLibrary
    get_reflection_engine() -> ReflectionEngine
    get_replan_engine()     -> ReplanEngine
    get_heartbeat_scheduler() -> HeartbeatScheduler | None  (None until bound)
    bind_heartbeat(action)  -> create the scheduler with the given action

The scheduler needs an ``action`` callback that knows how to start a run from
an objective; that callback lives in the orchestrator, so we let the
orchestrator bind it during agent_space.runtime.startup().
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from .episodic_memory import EpisodicMemory
from .heartbeat import HeartbeatJob, HeartbeatScheduler
from .reflection import ReflectionEngine
from .replan import ReplanEngine
from .skill_library import SkillLibrary

logger = logging.getLogger(__name__)


_episodic_memory: EpisodicMemory | None = None
_skill_library: SkillLibrary | None = None
_reflection_engine: ReflectionEngine | None = None
_replan_engine: ReplanEngine | None = None
_heartbeat_scheduler: HeartbeatScheduler | None = None


def get_episodic_memory() -> EpisodicMemory:
    global _episodic_memory
    if _episodic_memory is None:
        _episodic_memory = EpisodicMemory()
    return _episodic_memory


def get_skill_library() -> SkillLibrary:
    global _skill_library
    if _skill_library is None:
        memory = get_episodic_memory()

        async def _embed(text: str):
            return await memory._embed(text)  # type: ignore[attr-defined]

        _skill_library = SkillLibrary(embed_fn=_embed)
    return _skill_library


def get_reflection_engine() -> ReflectionEngine:
    global _reflection_engine
    if _reflection_engine is None:
        _reflection_engine = ReflectionEngine()
    return _reflection_engine


def get_replan_engine() -> ReplanEngine:
    global _replan_engine
    if _replan_engine is None:
        _replan_engine = ReplanEngine()
    return _replan_engine


def get_heartbeat_scheduler() -> HeartbeatScheduler | None:
    return _heartbeat_scheduler


def bind_heartbeat(
    action: Callable[[HeartbeatJob], Awaitable[dict[str, Any] | None]],
    *,
    tick_interval_seconds: float | None = None,
) -> HeartbeatScheduler:
    """Create the heartbeat scheduler with a real action and return it."""
    global _heartbeat_scheduler
    if _heartbeat_scheduler is not None:
        return _heartbeat_scheduler
    kwargs: dict[str, Any] = {"action": action}
    if tick_interval_seconds is not None:
        kwargs["tick_interval_seconds"] = float(tick_interval_seconds)
    _heartbeat_scheduler = HeartbeatScheduler(**kwargs)
    return _heartbeat_scheduler


async def shutdown() -> None:
    """Stop the heartbeat scheduler if running."""
    global _heartbeat_scheduler
    if _heartbeat_scheduler is None:
        return
    try:
        await _heartbeat_scheduler.stop()
    except Exception as exc:
        logger.debug("heartbeat shutdown error: %s", exc)
