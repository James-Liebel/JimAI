"""Application settings loaded from environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
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
OLLAMA_NPU_BASE_URL: str | None = os.getenv("OLLAMA_NPU_BASE_URL") or None

# Resolve paths relative to project root
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
CHROMA_FULL_PATH: Path = PROJECT_ROOT / CHROMA_PATH
KNOWLEDGE_GRAPH_FULL_PATH: Path = PROJECT_ROOT / KNOWLEDGE_GRAPH_PATH
STYLE_PROFILE_FULL_PATH: Path = PROJECT_ROOT / STYLE_PROFILE_PATH

# Rate limiting
RATE_LIMIT_RUN_MAX_CALLS: int = int(os.environ.get("RATE_LIMIT_RUN_MAX_CALLS", "10"))
RATE_LIMIT_RUN_WINDOW_SECS: float = float(os.environ.get("RATE_LIMIT_RUN_WINDOW_SECS", "60"))
RATE_LIMIT_ENABLED: bool = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() == "true"
