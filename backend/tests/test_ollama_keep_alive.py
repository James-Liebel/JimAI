"""Every model request must carry a finite keep_alive so Ollama evicts the model
after it goes idle. A missing or infinite ("-1") keep_alive is exactly how a loaded
model (e.g. the ~15 GB 32B) ends up resident indefinitely."""

import pytest

from config.settings import OLLAMA_KEEP_ALIVE_DEFAULT
from models import ollama_client

# Values that tell Ollama to keep a model resident forever (or that omit a timer).
_NEVER_EVICT = {"", "-1", "-1s", "0", "0s"}


@pytest.mark.anyio
async def test_generate_request_carries_configured_keep_alive(monkeypatch):
    captured: dict = {}

    async def _fake_stream(path, payload=None, base_url=None):
        captured["payload"] = payload
        yield {"response": "ok"}

    monkeypatch.setattr(ollama_client, "_stream_json_lines", _fake_stream)

    await ollama_client.generate_full(model="m", prompt="hi")

    assert captured["payload"]["keep_alive"] == OLLAMA_KEEP_ALIVE_DEFAULT


@pytest.mark.anyio
async def test_chat_request_carries_configured_keep_alive(monkeypatch):
    captured: dict = {}

    async def _fake_stream(path, payload=None, base_url=None):
        captured["payload"] = payload
        yield {"message": {"content": "ok"}}

    monkeypatch.setattr(ollama_client, "_stream_json_lines", _fake_stream)

    await ollama_client.chat_full(model="m", messages=[{"role": "user", "content": "hi"}])

    assert captured["payload"]["keep_alive"] == OLLAMA_KEEP_ALIVE_DEFAULT


def test_default_keep_alive_is_a_finite_eviction_window():
    assert OLLAMA_KEEP_ALIVE_DEFAULT not in _NEVER_EVICT
