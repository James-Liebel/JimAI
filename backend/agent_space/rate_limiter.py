"""Simple in-memory per-IP rate limiter for FastAPI endpoints."""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

# Configurable via env vars (imported from settings at use time)
_DEFAULT_MAX_CALLS = 10
_DEFAULT_WINDOW_SECS = 60.0


class _RateLimiter:
    """Sliding-window per-IP rate limiter."""

    def __init__(self, max_calls: int, window_secs: float) -> None:
        self.max_calls = max_calls
        self.window_secs = window_secs
        self._buckets: dict[str, deque[float]] = {}

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets.setdefault(key, deque())
        # Evict expired
        cutoff = now - self.window_secs
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.max_calls:
            return False
        bucket.append(now)
        return True

    def cleanup_old_keys(self, max_keys: int = 5000) -> None:
        """Remove stale keys to bound memory."""
        if len(self._buckets) <= max_keys:
            return
        now = time.monotonic()
        stale = [k for k, b in self._buckets.items() if not b or b[-1] < now - self.window_secs * 2]
        for k in stale:
            del self._buckets[k]


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


# Module-level singleton — configured lazily from settings
_run_limiter: _RateLimiter | None = None


def _get_run_limiter() -> _RateLimiter:
    global _run_limiter
    if _run_limiter is None:
        from config.settings import RATE_LIMIT_RUN_MAX_CALLS, RATE_LIMIT_RUN_WINDOW_SECS
        _run_limiter = _RateLimiter(
            max_calls=RATE_LIMIT_RUN_MAX_CALLS,
            window_secs=RATE_LIMIT_RUN_WINDOW_SECS,
        )
    return _run_limiter


async def check_run_rate_limit(request: Request) -> None:
    """FastAPI dependency: raise 429 if client is over the run-start rate limit."""
    limiter = _get_run_limiter()
    ip = _get_client_ip(request)
    limiter.cleanup_old_keys()
    if not limiter.is_allowed(ip):
        logger.warning(
            "Rate limit exceeded for runs/start: ip=%s max=%d window=%.0fs",
            ip,
            limiter.max_calls,
            limiter.window_secs,
        )
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": f"Too many run-start requests. Max {limiter.max_calls} per {int(limiter.window_secs)}s window.",
                "retry_after_seconds": int(limiter.window_secs),
            },
        )
