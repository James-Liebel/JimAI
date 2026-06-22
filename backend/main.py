"""Private AI Backend — FastAPI application entry point."""

import asyncio
import hmac
import inspect
import logging
import os
import subprocess
import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Receive, Scope, Send

from config.settings import LOG_LEVEL, BACKGROUND_AI_ENABLED
from models import ollama_client
from agent_space import background_tasks
from observability.logging_config import configure as configure_logging
from observability.middleware import RequestIdMiddleware

import httpx as _httpx

# Local-only posture: disable ChromaDB anonymized telemetry before any chromadb import.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

_HEALTH_HTTP: _httpx.AsyncClient | None = None
_CHROMA_CLIENT = None


def _health_client() -> _httpx.AsyncClient:
    global _HEALTH_HTTP
    if _HEALTH_HTTP is None or _HEALTH_HTTP.is_closed:
        _HEALTH_HTTP = _httpx.AsyncClient(timeout=5.0)
    return _HEALTH_HTTP


def _chroma_client():
    global _CHROMA_CLIENT
    if _CHROMA_CLIENT is None:
        import chromadb
        from chromadb.config import Settings
        # Local-only: disable Chroma's anonymized usage telemetry (no phone-home).
        _CHROMA_CLIENT = chromadb.Client(Settings(anonymized_telemetry=False))
    return _CHROMA_CLIENT

# Suppress known upstream Chroma/Pydantic Python 3.14 compatibility warning noise.
warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
    category=UserWarning,
)

# Configure logging (LOG_FORMAT=json for structured output; otherwise text with request_id).
configure_logging(LOG_LEVEL)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle.

    Uvicorn runs lifespan startup *before* binding the listen socket. Heavy Agent Space
    init (n8n, Qdrant warmup, etc.) can exceed launcher TCP probes unless we defer it.
    """
    logger.info("Starting Private AI backend...")

    ollama_ready = asyncio.Event()

    async def _connect_ollama_with_retry() -> None:
        """Probe Ollama with backoff so the first /health response reflects a warmed
        instance. Ollama on Windows can take 20–40s to bind 11434 (model index +
        GPU detect); without retries the backend would log 'not running' and the
        first frontend health poll would show ollama=false until ~5s later.

        Runs in the background so startup never blocks. Total wall-clock budget
        ~45s (8 attempts, 0.5→8s exponential capped). Sets ollama_ready when alive
        so dependent tasks (warmup) can wait rather than spawning into a void.
        """
        delays = [0.0, 0.5, 1.0, 2.0, 4.0, 6.0, 8.0, 8.0]
        for attempt, delay in enumerate(delays, start=1):
            if delay:
                await asyncio.sleep(delay)
            try:
                models = await ollama_client.list_models()
                logger.info("Ollama connected on attempt %d — %d models available", attempt, len(models))
                try:
                    from config.models import set_installed_models
                    set_installed_models(models)
                except Exception as exc:
                    logger.debug("set_installed_models skipped: %s", exc)
                ollama_ready.set()
                return
            except Exception as exc:  # noqa: BLE001 — any probe failure should be retried
                if attempt == len(delays):
                    logger.info("Ollama still not reachable after %d attempts: %s", attempt, exc)

    background_tasks.spawn(_connect_ollama_with_retry(), name="ollama_startup_probe")

    async def _agent_space_startup_task() -> None:
        try:
            from agent_space.runtime import startup as agent_space_startup

            await agent_space_startup()
            logger.info("Agent Space runtime initialized (background).")
        except Exception as exc:
            logger.warning("Agent Space startup warning: %s", exc)

    agent_space_bg = background_tasks.spawn(
        _agent_space_startup_task(), name="agent_space_startup"
    )

    async def _warm_models_task() -> None:
        """Preload the chat + embedding models into Ollama so the user's first
        message hits a warm model (saves several seconds of cold load on big
        Qwen/Llama variants). Failures are non-fatal — Ollama may not be up yet.
        """
        # Respect the global power switch: if the user has the AI turned off, don't
        # preload a model on startup — "off" should mean nothing loads on its own.
        try:
            from agent_space.runtime import power_manager
            if not power_manager.is_enabled():
                logger.info("Ollama warmup skipped: AI is powered off.")
                return
        except Exception:
            pass
        # Wait for the startup probe to confirm Ollama is live before warming.
        # Without this, the warmup would race the probe and silently fail on
        # cold start, leaving the user's first chat hit cold.
        try:
            await asyncio.wait_for(ollama_ready.wait(), timeout=50.0)
        except asyncio.TimeoutError:
            logger.info("Ollama warmup skipped: probe did not confirm readiness")
            return
        try:
            from models.router import get_model_config
            chat_cfg = get_model_config("chat")
            chat_model = getattr(chat_cfg, "model", None)
        except Exception:
            chat_model = None
        if not chat_model:
            return
        try:
            # Tiny no-op generate forces Ollama to load the model into VRAM/RAM.
            await ollama_client.generate_full(
                model=chat_model,
                prompt="ok",
                system="Reply with the single token 'ok'.",
                temperature=0.0,
                num_predict=1,
            )
            logger.info("Ollama chat model warmed: %s", chat_model)
        except Exception as exc:
            logger.info("Ollama chat warmup skipped: %s", exc)
        try:
            await ollama_client.embed("warmup")
            logger.info("Ollama embedding model warmed")
        except Exception:
            logger.debug("Ollama embed warmup skipped", exc_info=True)

    # Background AI (model warmup + autonomous reflection) is what touches Ollama
    # with no user action — and what holds a model in memory while idle. Gate both
    # behind JIMAI_BACKGROUND_AI so it can be turned off (e.g. while developing).
    if BACKGROUND_AI_ENABLED:
        background_tasks.spawn(_warm_models_task(), name="ollama_warmup")

        # Spawn the autonomous reflection loop. The loop self-rate-limits via an
        # idle-window check, so kicking it off at startup is cheap.
        try:
            from agents.thought_generator import start_background_loop
            start_background_loop()
            logger.info("Autonomous thought-generator loop started.")
        except Exception as exc:
            logger.debug("Autonomous thought loop not started: %s", exc)
    else:
        logger.info(
            "Background AI disabled (JIMAI_BACKGROUND_AI=0): skipping Ollama warmup "
            "and the autonomous reflection loop — models load on demand only."
        )
    try:
        yield
    finally:
        # Free VRAM/RAM on shutdown — without this the GPU keeps holding whichever
        # model was last used for OLLAMA_KEEP_ALIVE_DEFAULT, even though no client
        # is connected. Best-effort; failures are non-fatal.
        try:
            await ollama_client.unload_all_models()
        except Exception as exc:
            logger.debug("unload_all_models on shutdown skipped: %s", exc)
        if not agent_space_bg.done():
            try:
                await agent_space_bg
            except Exception as exc:
                logger.warning("Agent Space background startup did not finish cleanly: %s", exc)
        await background_tasks.drain(timeout=5.0)
        try:
            from agent_space.runtime import shutdown as agent_space_shutdown

            await agent_space_shutdown()
        except Exception as exc:
            logger.warning("Agent Space shutdown warning: %s", exc)
        global _HEALTH_HTTP
        if _HEALTH_HTTP is not None and not _HEALTH_HTTP.is_closed:
            await _HEALTH_HTTP.aclose()
        await ollama_client.close()
        logger.info("Backend shut down cleanly")


app = FastAPI(
    title="Private AI",
    description="Local-only AI system — no cloud APIs",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────

# Only widen CORS to the LAN/Tailnet when the operator has opted in (same condition as
# assert_safe_bind). By default the API answers localhost browser origins only.
_LAN_EXPOSURE = (
    os.getenv("JIMAI_ALLOW_INSECURE_LAN", "").lower() in ("1", "true", "yes")
    or bool(os.getenv("PRIVATE_AI_API_KEY", "").strip())
)


def _get_allowed_origins() -> list[str]:
    origins = [
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        # NOTE: the literal "null" origin is intentionally NOT allowed — it can be forged by
        # sandboxed iframes / data: URLs, which combined with allow_credentials=True would let
        # a hostile page make credentialed requests.
    ]
    if not _LAN_EXPOSURE:
        return origins
    try:
        result = subprocess.run(
            ["tailscale", "ip", "--4"],
            capture_output=True, text=True, timeout=3,
        )
        tailscale_ip = result.stdout.strip()
        if tailscale_ip:
            origins.extend([
                f"http://{tailscale_ip}:5173",
                f"http://{tailscale_ip}:8000",
            ])
    except Exception:
        pass
    return origins


# Loopback + RFC1918 + Tailscale-style 100.x — UI may be opened via LAN IP while list above is incomplete.
_LOCAL_UI_ORIGIN_REGEX = (
    r"^https?://("
    r"localhost|127\.0\.0\.1|\[::1\]|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}|"
    r"100\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r")(:\d+)?$"
)


class _NormalizeCorsPreflightMiddleware:
    """Starlette compares Access-Control-Request-Method case-sensitively against ALL_METHODS."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "OPTIONS":
            headers = MutableHeaders(scope=scope)
            key = "access-control-request-method"
            method = headers.get(key)
            if method:
                headers[key] = method.strip().upper()
        await self.app(scope, receive, send)


_cors_kwargs: dict = dict(
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# The broad RFC1918/Tailscale origin regex is enabled only when LAN exposure is opted in.
if _LAN_EXPOSURE:
    _cors_kwargs["allow_origin_regex"] = _LOCAL_UI_ORIGIN_REGEX
    if "allow_private_network" in inspect.signature(CORSMiddleware.__init__).parameters:
        _cors_kwargs["allow_private_network"] = True  # Starlette ≥0.38: PNA preflight
app.add_middleware(CORSMiddleware, **_cors_kwargs)
app.add_middleware(_NormalizeCorsPreflightMiddleware)

from agent_space.csrf_middleware import CSRFMiddleware
app.add_middleware(CSRFMiddleware)
app.add_middleware(RequestIdMiddleware)


# ── API key auth (scaffolded — disabled by default) ──────────────────

AUTH_REQUIRED = os.getenv("PRIVATE_AI_AUTH_REQUIRED", "false").lower() in ("1", "true", "yes")


async def verify_api_key(x_api_key: str = Header(None)) -> bool:
    # Default remains disabled unless PRIVATE_AI_AUTH_REQUIRED=true.
    if not AUTH_REQUIRED:
        return True
    expected = os.getenv("PRIVATE_AI_API_KEY", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="API auth is enabled but PRIVATE_AI_API_KEY is missing.",
        )
    if not hmac.compare_digest(x_api_key or "", expected):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


@app.middleware("http")
async def api_key_guard(request: Request, call_next):
    if not AUTH_REQUIRED:
        return await call_next(request)
    path = request.url.path
    if path in {"/health", "/docs", "/redoc", "/openapi.json"}:
        return await call_next(request)
    if path.startswith("/api/"):
        expected = os.getenv("PRIVATE_AI_API_KEY", "").strip()
        if not expected:
            return JSONResponse(
                status_code=503,
                content={"error": "API auth enabled but PRIVATE_AI_API_KEY is missing"},
            )
        provided = (request.headers.get("X-API-Key") or "").strip()
        if not hmac.compare_digest(provided, expected):
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid API key"},
            )
    return await call_next(request)


# ── Global exception handler ──────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log full detail server-side; return a generic message so internal paths, library
    # internals, or secrets embedded in exception text never reach the client.
    request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID")
    logger.error("Unhandled error (request_id=%s): %s", request_id, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "request_id": request_id},
    )


@app.exception_handler(ConnectionError)
async def connection_error_handler(request: Request, exc: ConnectionError):
    return JSONResponse(
        status_code=503,
        content={
            "error": str(exc),
            "type": "ConnectionError",
            "hint": "Is Ollama running? Start it with: ollama serve",
        },
    )


# ── Health check ───────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """System health check — reports status of Ollama, ChromaDB, and Qdrant."""
    from config.settings import OLLAMA_BASE_URL, normalize_ollama_base_url

    try:
        from agent_space.runtime import settings_store as agent_space_settings_store
        ollama_base_url = str(agent_space_settings_store.get().get("ollama_url") or OLLAMA_BASE_URL)
    except Exception:
        ollama_base_url = OLLAMA_BASE_URL

    ollama_probe_url = normalize_ollama_base_url(ollama_base_url)

    # Check Ollama (probe via IPv4 loopback when URL uses localhost — Windows IPv6 mismatch)
    ollama_ok = False
    try:
        resp = await _health_client().get(f"{ollama_probe_url}/api/tags")
        ollama_ok = resp.status_code < 500
    except Exception:
        ollama_ok = False

    # Check ChromaDB
    chromadb_ok = False
    try:
        _chroma_client().heartbeat()
        chromadb_ok = True
    except Exception:
        chromadb_ok = False

    # Check Qdrant
    qdrant_ok = False
    try:
        import socket
        sock = socket.create_connection(("localhost", 6333), timeout=3)
        sock.close()
        qdrant_ok = True
    except Exception:
        qdrant_ok = False

    return {
        "status": "ok",
        "services": {
            "ollama": ollama_ok,
            "chromadb": chromadb_ok,
            "qdrant": qdrant_ok,
        },
        "ollama_url": ollama_base_url,
        "version": "1.0.0",
    }


# ── Register routers ──────────────────────────────────────────────────
from api.chat import router as chat_router
from api.upload import router as upload_router
from api.vision import router as vision_router
from api.agents_api import router as agents_router
from api.teams_api import router as teams_router
from api.feedback import router as feedback_router
from api.completion import router as completion_router
from api.settings_api import router as settings_router
from api.system_agent_api import router as system_agent_router
from api.webtools import router as webtools_router
from api.autonomy_api import router as autonomy_router
from api.security_api import router as security_router
from api.users import router as users_router
from api.credentials import router as credentials_router
from agents.builder import router as builder_router
from agent_space.api import router as agent_space_router
from routers.github import router as github_router
from routers.workspace import router as workspace_router

app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(vision_router)
app.include_router(agents_router)
app.include_router(teams_router)
app.include_router(feedback_router)
app.include_router(completion_router)
app.include_router(settings_router)
app.include_router(system_agent_router)
app.include_router(webtools_router)
app.include_router(autonomy_router)
app.include_router(security_router)
app.include_router(users_router)
app.include_router(credentials_router)
app.include_router(builder_router)
app.include_router(agent_space_router)
app.include_router(github_router)
app.include_router(workspace_router)


# ── Prometheus metrics ─────────────────────────────────────────────────
from agent_space.metrics import get_metrics_output

@app.get("/metrics", include_in_schema=False)
async def metrics_endpoint():
    """Prometheus metrics exposition endpoint."""
    body, content_type = get_metrics_output()
    from fastapi.responses import Response
    return Response(content=body, media_type=content_type)


# ── Static frontend (single-origin hosting) ────────────────────────────
# Serve the built SPA from the backend so the entire app is ONE origin. That lets
# `tailscale serve https / http://127.0.0.1:8000` front everything with valid
# HTTPS — no CORS, no second port — while the backend stays loopback-bound (the
# assert_safe_bind guard is satisfied; nothing is exposed unauthenticated). This
# is a no-op in dev when frontend/dist has not been built (Vite serves the UI
# then). Mounted LAST so every API router and the health/metrics routes win.
from pathlib import Path as _Path

_FRONTEND_DIST = _Path(__file__).resolve().parent.parent / "frontend" / "dist"
# Paths that must keep their real (often 404) response instead of the SPA shell,
# so a stray API call or missing asset never gets a 200 HTML page back.
_NON_SPA_PREFIXES = ("api/", "assets/", "health", "metrics", "docs", "redoc", "openapi.json", "ws/")

if _FRONTEND_DIST.is_dir():
    from starlette.staticfiles import StaticFiles as _StaticFiles
    from starlette.responses import FileResponse as _FileResponse
    from starlette.exceptions import HTTPException as _StarletteHTTPException

    def _no_cache(response):
        """Force the SPA shell to revalidate. index.html references content-hashed
        asset bundles, so if the browser / service worker / installed PWA caches the
        shell, new builds never load — the stale shell keeps pointing at old bundles.
        Hashed files under /assets/ are immutable, so they stay cacheable as-is."""
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

    def _spa_shell_or_none(path: str):
        """index.html for a client-side route, else None (keep the real 404).

        Normalizes separators/leading slash so the prefix guard matches regardless
        of how Starlette hands us the sub-path — notably it uses os.sep, so on
        Windows the path arrives back-slashed (e.g. 'api\\foo')."""
        normalized = path.replace("\\", "/").lstrip("/")
        if normalized.startswith(_NON_SPA_PREFIXES):
            return None
        index = _FRONTEND_DIST / "index.html"
        return _no_cache(_FileResponse(index)) if index.is_file() else None

    class _SpaStaticFiles(_StaticFiles):
        """StaticFiles that falls back to index.html for client-side routes
        (e.g. /builder, /agents) so a hard refresh on a deep link still loads the
        SPA, while real asset 404s and API paths keep their normal response.

        Starlette signals a missing file by RAISING HTTPException(404) (not by
        returning one), so both branches are handled."""

        async def get_response(self, path, scope):
            try:
                response = await super().get_response(path, scope)
            except _StarletteHTTPException as exc:
                if exc.status_code == 404:
                    shell = _spa_shell_or_none(path)
                    if shell is not None:
                        return shell
                raise
            if response.status_code == 404:
                shell = _spa_shell_or_none(path)
                if shell is not None:
                    return shell
            # The HTML shell (index.html, including the root "/") must revalidate so
            # new builds load; hashed /assets/ files keep their default caching.
            if getattr(response, "media_type", None) == "text/html":
                return _no_cache(response)
            return response

    app.mount("/", _SpaStaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
    logger.info("Serving built frontend from %s (single-origin mode).", _FRONTEND_DIST)
