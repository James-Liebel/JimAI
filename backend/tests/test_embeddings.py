"""Embedding-client efficiency behavior: deterministic caching + batch embedding.

The model round-trip is mocked at the HTTP boundary (_request_with_retries), so
these assert the caching/batching contract — the observable efficiency behavior —
rather than talking to a live Ollama.
"""

import pytest

from models import ollama_client


class _FakeResp:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload


@pytest.fixture(autouse=True)
def _clear_embed_cache():
    ollama_client._EMBED_CACHE.clear()
    yield
    ollama_client._EMBED_CACHE.clear()


@pytest.mark.anyio
async def test_embed_serves_repeat_from_cache_without_second_call(monkeypatch):
    calls = {"n": 0}

    async def fake_request(method, path, *, base_url=None, json_payload=None):
        calls["n"] += 1
        return _FakeResp({"embedding": [0.1, 0.2, 0.3]})

    monkeypatch.setattr(ollama_client, "_request_with_retries", fake_request)

    await ollama_client.embed("same text")
    await ollama_client.embed("same text")

    assert calls["n"] == 1


@pytest.mark.anyio
async def test_embed_returns_correct_vector_on_cache_hit(monkeypatch):
    async def fake_request(method, path, *, base_url=None, json_payload=None):
        return _FakeResp({"embedding": [0.1, 0.2, 0.3]})

    monkeypatch.setattr(ollama_client, "_request_with_retries", fake_request)

    await ollama_client.embed("same text")
    assert await ollama_client.embed("same text") == [0.1, 0.2, 0.3]


@pytest.mark.anyio
async def test_mutating_returned_vector_does_not_corrupt_cache(monkeypatch):
    async def fake_request(method, path, *, base_url=None, json_payload=None):
        return _FakeResp({"embedding": [1.0, 2.0]})

    monkeypatch.setattr(ollama_client, "_request_with_retries", fake_request)

    first = await ollama_client.embed("x")
    first.append(999.0)

    assert await ollama_client.embed("x") == [1.0, 2.0]


@pytest.mark.anyio
async def test_embed_batch_returns_one_vector_per_input_in_order(monkeypatch):
    async def fake_request(method, path, *, base_url=None, json_payload=None):
        n = len(json_payload["input"])
        return _FakeResp({"embeddings": [[float(i)] for i in range(n)]})

    monkeypatch.setattr(ollama_client, "_request_with_retries", fake_request)

    assert await ollama_client.embed_batch(["a", "b", "c"]) == [[0.0], [1.0], [2.0]]


@pytest.mark.anyio
async def test_embed_batch_falls_back_to_sequential_when_endpoint_missing(monkeypatch):
    async def fake_request(method, path, *, base_url=None, json_payload=None):
        if path == "/api/embed":
            raise RuntimeError("404 not found")  # older Ollama without batch endpoint
        return _FakeResp({"embedding": [7.0]})

    monkeypatch.setattr(ollama_client, "_request_with_retries", fake_request)

    assert await ollama_client.embed_batch(["a", "b"]) == [[7.0], [7.0]]


@pytest.mark.anyio
async def test_embed_batch_empty_input_skips_call():
    assert await ollama_client.embed_batch([]) == []
