"""Private AI Backend — FastAPI application entry point."""

import logging
import os
import subprocess
import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from config.settings import LOG_LEVEL
from models import ollama_client

# Suppress known upstream Chroma/Pydantic Python 3.14 compatibility warning noise.
warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
    category=UserWarning,
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # Startup: validate Ollama connection (can auto-start later per app instance).
    logger.info("Starting Private AI backend...")
    try:
        models = await ollama_client.list_models()
        logger.info("Ollama connected — %d models available", len(models))
    except ConnectionError:
        logger.info("Ollama is not running at startup; it will auto-start on first app instance.")
    try:
        from agent_space.runtime import startup as agent_space_startup
        await agent_space_startup()
    except Exception as exc:
        logger.warning("Agent Space startup warning: %s", exc)
    yield
    # Shutdown: close HTTP client
    try:
        from agent_space.runtime import shutdown as agent_space_shutdown
        await agent_space_shutdown()
    except Exception as exc:
        logger.warning("Agent Space shutdown warning: %s", exc)
    await ollama_client.close()
    logger.info("Backend shut down cleanly")


app = FastAPI(
    title="Private AI",
    description="Local-only AI system — no cloud APIs",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────

def _get_allowed_origins() -> list[str]:
    origins = [
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ]
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


app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from agent_space.csrf_middleware import CSRFMiddleware
app.add_middleware(CSRFMiddleware)


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
    if x_api_key != expected:
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
        if provided != expected:
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid API key"},
            )
    return await call_next(request)


# ── Global exception handler ──────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "type": type(exc).__name__},
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
    import httpx

    from config.settings import OLLAMA_BASE_URL

    # Check Ollama
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            ollama_ok = resp.status_code < 500
    except Exception:
        ollama_ok = False

    # Check ChromaDB
    chromadb_ok = False
    try:
        import chromadb
        chroma_client = chromadb.Client()
        chroma_client.heartbeat()
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
        "version": "1.0.0",
    }


# ── Register routers ──────────────────────────────────────────────────
from api.chat import router as chat_router
from api.upload import router as upload_router
from api.vision import router as vision_router
from api.agents_api import router as agents_router
from api.feedback import router as feedback_router
from api.completion import router as completion_router
from api.settings_api import router as settings_router
from api.webtools import router as webtools_router
from agents.builder import router as builder_router
from agent_space.api import router as agent_space_router

app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(vision_router)
app.include_router(agents_router)
app.include_router(feedback_router)
app.include_router(completion_router)
app.include_router(settings_router)
app.include_router(webtools_router)
app.include_router(builder_router)
app.include_router(agent_space_router)


# ── Prometheus metrics ─────────────────────────────────────────────────
from agent_space.metrics import get_metrics_output

@app.get("/metrics", include_in_schema=False)
async def metrics_endpoint():
    """Prometheus metrics exposition endpoint."""
    body, content_type = get_metrics_output()
    from fastapi.responses import Response
    return Response(content=body, media_type=content_type)
