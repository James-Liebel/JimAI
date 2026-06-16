"""Application settings loaded from environment variables."""

import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)


def normalize_ollama_base_url(url: str) -> str:
    """Use 127.0.0.1 instead of localhost/::1 so HTTP clients hit IPv4 (Ollama on Windows is often IPv4-only)."""
    raw = (url or "").strip().rstrip("/")
    if not raw:
        return raw
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host in ("localhost", "::1"):
        port = parsed.port
        netloc = f"127.0.0.1:{port}" if port else "127.0.0.1"
        return urlunparse(
            (parsed.scheme or "http", netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
        ).rstrip("/")
    return raw


_DEFAULT_OLLAMA = "http://127.0.0.1:11434"
OLLAMA_BASE_URL: str = normalize_ollama_base_url(os.getenv("OLLAMA_BASE_URL", _DEFAULT_OLLAMA))
# How long Ollama should keep a model resident after its last request. Short value =
# less VRAM held idle and the GPU cools off between roles. Pass any Ollama-accepted
# duration string ("60s", "5m") or "0" to evict immediately. Used as the default by
# every ollama_client call that doesn't override it.
OLLAMA_KEEP_ALIVE_DEFAULT: str = os.getenv("OLLAMA_KEEP_ALIVE_DEFAULT", "60s")
# Browser/Atlas agent — its loop spans many short requests with think-time gaps,
# so it gets its own knob. Still much shorter than the previous 10m default.
OLLAMA_BROWSER_KEEP_ALIVE: str = os.getenv("OLLAMA_BROWSER_KEEP_ALIVE", "120s")
# Background AI that touches Ollama with NO user action: the startup model warmup
# and the autonomous "thought generator" reflection loop. These keep a model
# resident (and the GPU warm) while you're idle. Set JIMAI_BACKGROUND_AI=0 to turn
# them off — e.g. while developing on this repo — so Ollama only loads a model when
# you actually send a request, then evicts it per OLLAMA_KEEP_ALIVE_DEFAULT.
BACKGROUND_AI_ENABLED: bool = os.getenv("JIMAI_BACKGROUND_AI", "true").lower() in ("true", "1", "yes")
BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
N8N_BASE_URL: str = os.getenv("N8N_BASE_URL", "http://localhost:5678")
QDRANT_BASE_URL: str = os.getenv("QDRANT_BASE_URL", "http://localhost:6333")
SEARXNG_BASE_URL: str = os.getenv("SEARXNG_BASE_URL", "")
JUPYTER_BASE_URL: str = os.getenv("JUPYTER_BASE_URL", "http://localhost:8888")
GRAFANA_BASE_URL: str = os.getenv("GRAFANA_BASE_URL", "http://localhost:3000")
CHROMA_PATH: str = os.getenv("CHROMA_PATH", "./chroma_db")
KNOWLEDGE_GRAPH_PATH: str = os.getenv("KNOWLEDGE_GRAPH_PATH", "./data/graph.json")
STYLE_PROFILE_PATH: str = os.getenv("STYLE_PROFILE_PATH", "./data/style_profile.json")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# ── Model layering (confirm outputs / run models against each other) ─────
LAYERED_REVIEW_ENABLED: bool = os.getenv("LAYERED_REVIEW_ENABLED", "false").lower() in ("true", "1", "yes")
REVIEW_MODEL_ROLE: str = os.getenv("REVIEW_MODEL_ROLE", "chat")
COMPARE_MODELS_ENABLED: bool = os.getenv("COMPARE_MODELS_ENABLED", "false").lower() in ("true", "1", "yes")
# Optional overrides; if unset, compare pipeline is chosen from prompt context (see router.get_compare_pipeline)
COMPARE_MODEL_A_ROLE: str | None = os.getenv("COMPARE_MODEL_A_ROLE") or None
COMPARE_MODEL_B_ROLE: str | None = os.getenv("COMPARE_MODEL_B_ROLE") or None
JUDGE_MODEL_ROLE: str = os.getenv("JUDGE_MODEL_ROLE", "chat")

# Optional second Ollama endpoint (e.g. NPU or CPU instance) — when set, compare model B and/or review run here to spread load
_npu_raw = os.getenv("OLLAMA_NPU_BASE_URL") or None
OLLAMA_NPU_BASE_URL: str | None = normalize_ollama_base_url(_npu_raw) if _npu_raw else None

# Resolve paths relative to project root
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
CHROMA_FULL_PATH: Path = PROJECT_ROOT / CHROMA_PATH
KNOWLEDGE_GRAPH_FULL_PATH: Path = PROJECT_ROOT / KNOWLEDGE_GRAPH_PATH
STYLE_PROFILE_FULL_PATH: Path = PROJECT_ROOT / STYLE_PROFILE_PATH

# Browser / web extraction
BROWSER_EXTRACT_MAX_CHARS: int = int(os.environ.get("BROWSER_EXTRACT_MAX_CHARS", "8000"))

# Rate limiting
RATE_LIMIT_RUN_MAX_CALLS: int = int(os.environ.get("RATE_LIMIT_RUN_MAX_CALLS", "10"))
RATE_LIMIT_RUN_WINDOW_SECS: float = float(os.environ.get("RATE_LIMIT_RUN_WINDOW_SECS", "60"))
RATE_LIMIT_ENABLED: bool = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() in ("true", "1", "yes")


# ── Network bind safety ──────────────────────────────────────────────────
def is_loopback_host(host: str) -> bool:
    """True for localhost-equivalent bind hosts (any 127.0.0.0/8 address, ::1, localhost)."""
    h = (host or "").strip().lower()
    if h.startswith("["):  # bracketed IPv6, e.g. [::1]:8000
        h = h[1:].split("]", 1)[0]
    elif h.count(":") == 1:  # host:port (not bare IPv6)
        h = h.split(":", 1)[0]
    return h in {"", "localhost", "::1"} or h.startswith("127.")


def assert_safe_bind(host: str) -> None:
    """Fail closed when binding a non-loopback interface without authentication.

    The backend exposes code-execution, arbitrary file-read, and system-agent
    endpoints. Binding to 0.0.0.0 / a LAN / a Tailnet with auth disabled would
    make all of them reachable unauthenticated, so refuse unless the operator
    has set an API key or explicitly accepted the risk.
    """
    if is_loopback_host(host):
        return
    if os.getenv("JIMAI_ALLOW_INSECURE_LAN", "").lower() in ("1", "true", "yes"):
        return
    auth_required = os.getenv("PRIVATE_AI_AUTH_REQUIRED", "false").lower() in ("1", "true", "yes")
    has_key = bool(os.getenv("PRIVATE_AI_API_KEY", "").strip())
    if auth_required and has_key:
        return
    raise SystemExit(
        f"\n[SECURITY] Refusing to bind to non-loopback host '{host}' without authentication.\n"
        "This would expose code-execution, file-read, and system-agent endpoints to your LAN/Tailnet.\n"
        "Choose one:\n"
        "  - bind to 127.0.0.1 (default, recommended), or\n"
        "  - set PRIVATE_AI_AUTH_REQUIRED=true and PRIVATE_AI_API_KEY=<strong-key>, or\n"
        "  - set JIMAI_ALLOW_INSECURE_LAN=1 to explicitly accept the risk.\n"
    )
