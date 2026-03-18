"""
CSRF protection via custom request header.

For local-first apps: cross-site requests cannot set custom headers due to browser
CORS preflight rules. Checking for X-Requested-With or X-JimAI-CSRF header provides
meaningful protection against cross-site HTML form submissions (which cannot send custom
headers). This is appropriate for a localhost-served app.

Exclusions (documented):
- GET, HEAD, OPTIONS: safe methods, no state change
- /health, /docs, /openapi.json: public/infra endpoints
- /api/agent-space/research/stream: SSE streaming (browser EventSource cannot set headers)
- /api/agent-space/runs/events: SSE streaming endpoint
- CSRF_ENABLED=false (env var): for Electron or API-only clients that cannot set headers
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

CSRF_ENABLED = os.environ.get("CSRF_ENABLED", "true").lower() == "true"
CSRF_HEADER = "X-JimAI-CSRF"
CSRF_HEADER_VALUE = "1"

# Endpoints excluded from CSRF check (documented above)
_SAFE_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc", "/metrics")
_SAFE_PATH_FRAGMENTS = ("/events", "/stream", "/research/stream", "/sse")
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _is_exempt(request: Request) -> bool:
    if request.method in _SAFE_METHODS:
        return True
    path = request.url.path
    if any(path.startswith(p) for p in _SAFE_PREFIXES):
        return True
    if any(f in path for f in _SAFE_PATH_FRAGMENTS):
        return True
    return False


class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if not CSRF_ENABLED or _is_exempt(request):
            return await call_next(request)

        header_val = request.headers.get(CSRF_HEADER)
        if header_val != CSRF_HEADER_VALUE:
            logger.warning(
                "CSRF check failed: method=%s path=%s ip=%s header_present=%s",
                request.method,
                request.url.path,
                request.client.host if request.client else "unknown",
                header_val is not None,
            )
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=403,
                content={
                    "error": "csrf_rejected",
                    "message": f"Missing or invalid {CSRF_HEADER} header.",
                    "hint": "Add header: X-JimAI-CSRF: 1 to all state-changing requests, or set CSRF_ENABLED=false.",
                },
            )
        return await call_next(request)
