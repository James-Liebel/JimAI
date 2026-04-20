"""Async Ollama HTTP client — all model inference goes through here."""

import asyncio
import json
import logging
from typing import AsyncGenerator

import httpx

from config.settings import OLLAMA_BASE_URL, OLLAMA_NPU_BASE_URL

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None
_npu_client: httpx.AsyncClient | None = None
RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 0.35


def _is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = int(exc.response.status_code) if exc.response is not None else 0
        return code in {408, 409, 425, 429, 500, 502, 503, 504}
    return False


async def _request_with_retries(
    method: str,
    path: str,
    *,
    base_url: str | None = None,
    json_payload: dict | None = None,
) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        client = await _get_client(base_url)
        try:
            resp = await client.request(method, path, json=json_payload)
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: PERF203
            last_exc = exc
            if attempt >= RETRY_ATTEMPTS or not _is_retryable_error(exc):
                break
            await asyncio.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
    assert last_exc is not None
    raise last_exc


async def _stream_json_lines(
    path: str,
    *,
    payload: dict,
    base_url: str | None = None,
) -> AsyncGenerator[dict, None]:
    last_exc: Exception | None = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        client = await _get_client(base_url)
        try:
            async with client.stream("POST", path, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        parsed = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    yield parsed
                    if parsed.get("done"):
                        return
            return
        except Exception as exc:  # noqa: PERF203
            last_exc = exc
            if attempt >= RETRY_ATTEMPTS or not _is_retryable_error(exc):
                break
            await asyncio.sleep(RETRY_BASE_DELAY_SECONDS * attempt)
    assert last_exc is not None
    raise last_exc


async def _get_client(base_url: str | None = None) -> httpx.AsyncClient:
    """Lazy-init shared async HTTP client. Use base_url (e.g. OLLAMA_NPU_BASE_URL) to target NPU/second instance."""
    global _client, _npu_client
    if base_url and base_url.strip():
        if _npu_client is None or _npu_client.is_closed:
            _npu_client = httpx.AsyncClient(
                base_url=base_url.rstrip("/"),
                timeout=httpx.Timeout(120.0, connect=10.0),
            )
            logger.info("Using secondary Ollama endpoint (e.g. NPU): %s", base_url)
        return _npu_client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=OLLAMA_BASE_URL,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
    return _client


def _build_chat_messages(
    history: list[dict],
    current_content: str,
    system: str = "",
    images: list[str] | None = None,
    max_history_turns: int = 20,
    max_total_chars: int | None = None,
) -> list[dict]:
    """Build messages for /api/chat: system + capped history + current user message."""
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    # Use last N messages so the model sees recent context without overflowing
    capped = history[-max_history_turns:] if len(history) > max_history_turns else list(history)
    if max_total_chars is not None and max_total_chars > 0:
        while len(capped) > 2:
            total = sum(len(str(m.get("content") or "")) for m in capped)
            if total <= max_total_chars:
                break
            capped = capped[1:]
    for m in capped:
        role = m.get("role")
        content = m.get("content") or ""
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    # Current user message (optionally with images)
    user_msg: dict = {"role": "user", "content": current_content}
    if images:
        user_msg["images"] = images
    messages.append(user_msg)
    return messages


async def chat_stream(
    model: str,
    messages: list[dict],
    stream: bool = True,
    temperature: float = 0.7,
    num_ctx: int | None = None,
    num_predict: int | None = None,
    num_batch: int | None = None,
    repeat_penalty: float = 1.1,
    think: bool | None = None,
    keep_alive: str = "30m",
    base_url: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream assistant reply using Ollama /api/chat. base_url: use NPU/second instance when set (e.g. OLLAMA_NPU_BASE_URL)."""
    options: dict = {"temperature": temperature, "repeat_penalty": repeat_penalty}
    if num_ctx is not None:
        options["num_ctx"] = num_ctx
    if num_predict is not None:
        options["num_predict"] = num_predict
    if num_batch is not None:
        options["num_batch"] = num_batch
    if think is not None:
        options["think"] = think
    payload: dict = {
        "model": model,
        "messages": messages,
        "stream": stream,
        "keep_alive": keep_alive,
        "options": options,
    }
    try:
        async for chunk in _stream_json_lines("/api/chat", payload=payload, base_url=base_url):
            msg = chunk.get("message") or {}
            if "content" in msg and msg["content"]:
                yield msg["content"]
    except httpx.ConnectError:
        raise ConnectionError(
            "Ollama is not running. Start it with: ollama serve"
        )


async def chat_full(
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    num_ctx: int | None = None,
    num_predict: int | None = None,
    num_batch: int | None = None,
    repeat_penalty: float = 1.1,
    think: bool | None = None,
    keep_alive: str = "30m",
    base_url: str | None = None,
) -> str:
    """Non-streaming: return full assistant reply from /api/chat. base_url: NPU/second instance when set."""
    parts: list[str] = []
    async for chunk in chat_stream(
        model=model,
        messages=messages,
        stream=True,
        temperature=temperature,
        num_ctx=num_ctx,
        num_predict=num_predict,
        num_batch=num_batch,
        repeat_penalty=repeat_penalty,
        think=think,
        keep_alive=keep_alive,
        base_url=base_url,
    ):
        parts.append(chunk)
    return "".join(parts)


async def generate(
    model: str,
    prompt: str,
    system: str = "",
    stream: bool = True,
    images: list[str] | None = None,
    temperature: float | None = None,
    num_ctx: int | None = None,
    num_predict: int | None = None,
    num_batch: int | None = None,
    repeat_penalty: float = 1.1,
    keep_alive: str = "30m",
    base_url: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream text chunks from Ollama /api/generate. base_url: NPU/second instance when set."""
    options: dict = {"repeat_penalty": repeat_penalty}
    if temperature is not None:
        options["temperature"] = temperature
    if num_ctx is not None:
        options["num_ctx"] = num_ctx
    if num_predict is not None:
        options["num_predict"] = num_predict
    if num_batch is not None:
        options["num_batch"] = num_batch
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "stream": stream,
        "keep_alive": keep_alive,
        "options": options,
    }
    if system:
        payload["system"] = system
    if images:
        payload["images"] = images

    try:
        async for chunk in _stream_json_lines("/api/generate", payload=payload, base_url=base_url):
            if "response" in chunk:
                yield chunk["response"]
    except httpx.ConnectError:
        raise ConnectionError(
            "Ollama is not running. Start it with: ollama serve"
        )


async def generate_full(
    model: str,
    prompt: str,
    system: str = "",
    images: list[str] | None = None,
    temperature: float = 0.7,
    num_ctx: int | None = None,
    num_predict: int | None = None,
    num_batch: int | None = None,
    repeat_penalty: float = 1.1,
) -> str:
    """Non-streaming convenience wrapper — returns the full response as a string."""
    parts: list[str] = []
    async for chunk in generate(
        model=model,
        prompt=prompt,
        system=system,
        stream=True,
        images=images,
        temperature=temperature,
        num_ctx=num_ctx,
        num_predict=num_predict,
        num_batch=num_batch,
        repeat_penalty=repeat_penalty,
    ):
        parts.append(chunk)
    return "".join(parts)


async def embed(text: str) -> list[float]:
    """Get an embedding vector from nomic-embed-text via /api/embeddings."""
    try:
        resp = await _request_with_retries(
            "POST",
            "/api/embeddings",
            json_payload={"model": "nomic-embed-text", "prompt": text},
        )
        data = resp.json()
        return data.get("embedding", [])
    except httpx.ConnectError:
        raise ConnectionError(
            "Ollama is not running. Start it with: ollama serve"
        )


async def list_models() -> list[str]:
    """Return names of all locally-available Ollama models."""
    try:
        resp = await _request_with_retries("GET", "/api/tags")
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]
    except httpx.ConnectError:
        raise ConnectionError(
            "Ollama is not running. Start it with: ollama serve"
        )


async def unload_model(model: str) -> None:
    """Free VRAM by telling Ollama to unload a model (keep_alive=0)."""
    try:
        await _request_with_retries(
            "POST",
            "/api/generate",
            json_payload={"model": model, "prompt": "", "keep_alive": 0},
        )
        logger.info("Unloaded model %s from VRAM", model)
    except httpx.ConnectError:
        logger.warning("Could not unload %s — Ollama not reachable", model)


async def unload_all_models() -> None:
    """Unload all models to free VRAM before loading the 32B deep model."""
    for model in [
        "qwen3:14b",
        "qwen2.5-coder:14b",
        "qwen3:8b",
        "qwen2.5vl:7b",
        "qwen2-math:7b-instruct",
        "qwen2.5-coder:7b",
        "qwen2.5-coder:3b",
        # legacy names — harmless if not loaded
        "deepseek-r1:14b",
        "qwen2.5:32b",
    ]:
        try:
            await unload_model(model)
        except Exception:
            pass


async def prepare_for_deep_mode() -> None:
    """Must be called before any qwen2.5:32b-instruct-q3_k_s request."""
    await unload_all_models()
    await asyncio.sleep(0.5)  # give VRAM time to free


async def close() -> None:
    """Shut down the shared HTTP clients cleanly."""
    global _client, _npu_client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
    if _npu_client and not _npu_client.is_closed:
        await _npu_client.aclose()
        _npu_client = None
