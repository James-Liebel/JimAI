"""Process-wide registry for fire-and-forget asyncio tasks.

Without registration, asyncio drops the task's strong reference as soon as
create_task returns, so a GC cycle can cancel the coroutine before it
finishes. The registry holds a strong ref until the task completes and
drains pending tasks on lifespan shutdown.
"""

import asyncio
import logging
from typing import Coroutine

logger = logging.getLogger(__name__)

_TASKS: set[asyncio.Task] = set()


def spawn(coro: Coroutine, *, name: str | None = None) -> asyncio.Task:
    task = asyncio.create_task(coro, name=name)
    _TASKS.add(task)
    task.add_done_callback(_on_done)
    return task


def _on_done(task: asyncio.Task) -> None:
    _TASKS.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.warning("background task %r failed: %s", task.get_name(), exc, exc_info=exc)


async def drain(timeout: float = 5.0) -> None:
    if not _TASKS:
        return
    pending = list(_TASKS)
    logger.info("draining %d background tasks (timeout=%.1fs)", len(pending), timeout)
    _, still_pending = await asyncio.wait(pending, timeout=timeout)
    for t in still_pending:
        t.cancel()
    if still_pending:
        logger.warning("%d background tasks did not complete; cancelled", len(still_pending))
