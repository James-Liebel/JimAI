"""list_loaded_models(): the VRAM-occupancy probe behind the activity status."""

from __future__ import annotations

import pytest

from models import ollama_client


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload=None, raise_exc=None):
        self._payload = payload
        self._raise = raise_exc

    async def get(self, _path):
        if self._raise:
            raise self._raise
        return _FakeResp(self._payload)


@pytest.mark.anyio
async def test_returns_loaded_model_names(monkeypatch):
    async def _client(*_a, **_k):
        return _FakeClient(payload={"models": [{"name": "qwen3:8b"}, {"model": "qwen2.5-coder:14b"}]})

    monkeypatch.setattr(ollama_client, "_get_client", _client)
    assert await ollama_client.list_loaded_models() == ["qwen3:8b", "qwen2.5-coder:14b"]


@pytest.mark.anyio
async def test_empty_when_nothing_loaded(monkeypatch):
    async def _client(*_a, **_k):
        return _FakeClient(payload={"models": []})

    monkeypatch.setattr(ollama_client, "_get_client", _client)
    assert await ollama_client.list_loaded_models() == []


@pytest.mark.anyio
async def test_empty_when_ollama_unreachable(monkeypatch):
    async def _client(*_a, **_k):
        return _FakeClient(raise_exc=RuntimeError("connection refused"))

    monkeypatch.setattr(ollama_client, "_get_client", _client)
    # Unreachable Ollama => report nothing loaded rather than raising.
    assert await ollama_client.list_loaded_models() == []
