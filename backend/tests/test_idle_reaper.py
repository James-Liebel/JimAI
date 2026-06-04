"""Idle Ollama reaper: free VRAM / stop Ollama when there's nothing to serve,
but never while an autonomous run is still working."""

from __future__ import annotations

import time

import pytest

from agent_space.instance_lifecycle import InstanceLifecycleManager


@pytest.fixture(autouse=True)
def _patch_ollama(monkeypatch):
    """Record unload calls and never touch a real Ollama / process."""
    calls = {"unload": 0, "stop": 0}

    async def _fake_unload_all():
        calls["unload"] += 1

    monkeypatch.setattr("agent_space.instance_lifecycle.ollama_client.unload_all_models", _fake_unload_all)
    yield calls


def _idle_armed_manager() -> InstanceLifecycleManager:
    """A manager with no clients and a stop timer already due."""
    mgr = InstanceLifecycleManager(stop_grace_seconds=12)
    mgr._instances.clear()
    mgr._pending_stop_at = time.time() - 1  # already past the grace deadline
    return mgr


def test_runs_active_defaults_false_without_predicate():
    mgr = InstanceLifecycleManager()
    assert mgr._runs_active() is False


def test_broken_active_predicate_keeps_ollama_up():
    mgr = InstanceLifecycleManager()

    def boom() -> bool:
        raise RuntimeError("orchestrator unavailable")

    mgr.set_active_run_check(boom)
    # Safer to defer cleanup than risk killing a live run.
    assert mgr._runs_active() is True


@pytest.mark.anyio
async def test_reaps_when_idle_and_no_active_run(_patch_ollama):
    mgr = _idle_armed_manager()
    mgr.set_active_run_check(lambda: False)
    await mgr.tick()
    assert _patch_ollama["unload"] == 1
    assert mgr._pending_stop_at is None


@pytest.mark.anyio
async def test_defers_reaping_while_run_active(_patch_ollama):
    mgr = _idle_armed_manager()
    mgr.set_active_run_check(lambda: True)  # a job is still working
    await mgr.tick()
    assert _patch_ollama["unload"] == 0  # model kept resident for the live run
    assert mgr._pending_stop_at is not None  # timer re-armed to re-check later
