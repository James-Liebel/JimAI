"""Background reflection must stay cheap and obey the global power switch."""

import pytest

from agents import thought_generator
from config.models import TURBO_CONFIGS


@pytest.mark.anyio
async def test_reflect_once_loads_no_model_when_powered_off(monkeypatch):
    monkeypatch.setattr(thought_generator, "_ai_power_enabled", lambda: False)

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("model must not load while the AI is powered off")

    monkeypatch.setattr(thought_generator.ollama_client, "generate_full", _fail_if_called)

    result = await thought_generator.reflect_once("test-user")

    assert result == {}


@pytest.mark.anyio
async def test_reflect_once_uses_small_background_model(monkeypatch):
    monkeypatch.setattr(thought_generator, "_ai_power_enabled", lambda: True)

    async def _fragments(user_id, n=12):
        return [
            "fragment a: the user is building a local AI workspace",
            "fragment b: they care about GPU memory while the app is idle",
            "fragment c: phone access is over Tailscale",
            "fragment d: the chat UI must fill the screen edge to edge",
            "fragment e: background reflection should be cheap",
        ]

    monkeypatch.setattr(thought_generator, "_collect_recent_fragments", _fragments)
    monkeypatch.setattr(thought_generator, "_persist_batch", lambda *a, **k: None)

    captured: dict[str, str] = {}

    async def _capture(*args, **kwargs):
        captured["model"] = kwargs["model"]
        return '{"connections": ["fragment a and fragment e point to a low-overhead goal"]}'

    monkeypatch.setattr(thought_generator.ollama_client, "generate_full", _capture)

    await thought_generator.reflect_once("test-user")

    assert captured["model"] == TURBO_CONFIGS["chat"].model
