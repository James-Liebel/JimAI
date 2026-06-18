"""Hard idle guarantee: once generation has been idle past the window, every
model is unloaded — even while the app stays connected, independent of Ollama's
keep_alive."""

import time

import pytest

from agent_space.instance_lifecycle import InstanceLifecycleManager
from models import ollama_client


@pytest.fixture(autouse=True)
def _reset_generation_state():
    ollama_client._inflight_generations = 0
    ollama_client._last_generation_ts = 0.0
    ollama_client._idle_unloaded_for_ts = -1.0
    yield
    ollama_client._inflight_generations = 0
    ollama_client._last_generation_ts = 0.0
    ollama_client._idle_unloaded_for_ts = -1.0


@pytest.fixture
def _record_unload(monkeypatch):
    calls = {"n": 0}

    async def _fake_unload_all():
        calls["n"] += 1

    monkeypatch.setattr(ollama_client, "unload_all_models", _fake_unload_all)
    return calls


@pytest.mark.anyio
async def test_unloads_after_idle_window(_record_unload):
    ollama_client._last_generation_ts = time.time() - 1000
    await ollama_client.unload_idle_models(90)
    assert _record_unload["n"] == 1


@pytest.mark.anyio
async def test_keeps_model_within_idle_window(_record_unload):
    ollama_client._last_generation_ts = time.time()
    await ollama_client.unload_idle_models(90)
    assert _record_unload["n"] == 0


@pytest.mark.anyio
async def test_never_unloads_while_generation_in_flight(_record_unload):
    ollama_client._last_generation_ts = time.time() - 1000
    ollama_client._inflight_generations = 1
    await ollama_client.unload_idle_models(90)
    assert _record_unload["n"] == 0


@pytest.mark.anyio
async def test_unloads_only_once_per_idle_period(_record_unload):
    ollama_client._last_generation_ts = time.time() - 1000
    await ollama_client.unload_idle_models(90)
    await ollama_client.unload_idle_models(90)
    assert _record_unload["n"] == 1


@pytest.mark.anyio
async def test_tick_unloads_idle_models_while_app_connected(monkeypatch):
    called = {"n": 0}

    async def _fake_unload_idle(window):
        called["n"] += 1
        return False

    monkeypatch.setattr(
        "agent_space.instance_lifecycle.ollama_client.unload_idle_models",
        _fake_unload_idle,
    )
    mgr = InstanceLifecycleManager()
    monkeypatch.setattr(mgr, "_persist_state_locked", lambda: None)
    mgr._instances.clear()
    mgr._instances["live"] = {
        "instance_id": "live",
        "client": "ui",
        "metadata": {},
        "created_at": time.time(),
        "last_seen_at": time.time(),
    }
    mgr._pending_stop_at = None
    mgr.set_active_run_check(lambda: False)

    await mgr.tick()

    assert called["n"] == 1
