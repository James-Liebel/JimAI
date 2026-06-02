"""Global generation kill-switch (thermal-safety pause) for the Ollama client.

These cover the cooperative abort wired to the PowerManager: when the predicate
trips, a new generation must not even open a connection, and an in-flight stream
must stop yielding (which closes the HTTP connection and frees the GPU).
"""

from __future__ import annotations

import pytest

from models import ollama_client


@pytest.fixture(autouse=True)
def _reset_abort_check():
    """Each test owns the global hook; always restore it to off afterwards."""
    yield
    ollama_client.set_global_abort_check(None)


def test_should_abort_false_when_unset():
    ollama_client.set_global_abort_check(None)
    assert ollama_client._should_abort() is False


def test_should_abort_reflects_predicate():
    ollama_client.set_global_abort_check(lambda: True)
    assert ollama_client._should_abort() is True


def test_should_abort_swallows_predicate_errors():
    def boom() -> bool:
        raise RuntimeError("power file unreadable")

    ollama_client.set_global_abort_check(boom)
    # A broken predicate must never wedge generation — default to "don't abort".
    assert ollama_client._should_abort() is False


@pytest.mark.anyio
async def test_stream_suppressed_while_paused_opens_no_connection(monkeypatch):
    """While paused, _stream_json_lines must yield nothing and never call _get_client."""
    ollama_client.set_global_abort_check(lambda: True)

    called = False

    async def _fail_get_client(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("must not open a client while paused")

    monkeypatch.setattr(ollama_client, "_get_client", _fail_get_client)

    chunks = [c async for c in ollama_client._stream_json_lines("/api/chat", payload={})]
    assert chunks == []
    assert called is False
