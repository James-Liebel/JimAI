import asyncio

import pytest

from agent_space import background_tasks


@pytest.mark.anyio
async def test_spawn_runs_and_drains():
    flag = {"done": False}

    async def _w():
        await asyncio.sleep(0.01)
        flag["done"] = True

    background_tasks.spawn(_w())
    await background_tasks.drain(timeout=1.0)
    assert flag["done"]


@pytest.mark.anyio
async def test_drain_cancels_hangers():
    async def _hang():
        await asyncio.sleep(10)

    background_tasks.spawn(_hang())
    await background_tasks.drain(timeout=0.1)
    # returns without error; hanging task was cancelled


@pytest.mark.anyio
async def test_failed_task_does_not_propagate():
    async def _boom():
        raise RuntimeError("expected")

    background_tasks.spawn(_boom())
    await background_tasks.drain(timeout=1.0)
