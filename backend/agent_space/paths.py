"""Shared filesystem paths for Agent Space."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _can_write_root(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f".write_probe_{uuid.uuid4().hex}.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _resolve_data_root() -> Path:
    override = os.getenv("AGENT_SPACE_DATA_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    project_data_root = PROJECT_ROOT / "data" / "agent_space"
    if _can_write_root(project_data_root):
        return project_data_root

    # Fallback for restricted environments where repo-level data is read-only.
    return BACKEND_ROOT / "data" / "agent_space"


DATA_ROOT = _resolve_data_root()
REVIEWS_DIR = DATA_ROOT / "reviews"
SNAPSHOTS_DIR = DATA_ROOT / "snapshots"
LOGS_DIR = DATA_ROOT / "logs"
INDEX_DIR = DATA_ROOT / "index"
MEMORY_DIR = DATA_ROOT / "memory"
CHATS_DIR = DATA_ROOT / "chats"
EXPORTS_DIR = DATA_ROOT / "exports"
RUNTIME_DIR = DATA_ROOT / "runtime"
TEAMS_DIR = DATA_ROOT / "teams"
WORKFLOWS_DIR = DATA_ROOT / "workflows"
SKILLS_DIR = DATA_ROOT / "skills"
SECURE_DIR = DATA_ROOT / "secure"
GENERATED_DIR = DATA_ROOT / "generated"
SELF_IMPROVEMENT_DIR = DATA_ROOT / "self_improvement"


def ensure_layout() -> None:
    """Create Agent Space data directories if they do not exist."""
    for path in (
        DATA_ROOT,
        REVIEWS_DIR,
        SNAPSHOTS_DIR,
        LOGS_DIR,
        INDEX_DIR,
        MEMORY_DIR,
        CHATS_DIR,
        EXPORTS_DIR,
        RUNTIME_DIR,
        TEAMS_DIR,
        WORKFLOWS_DIR,
        SKILLS_DIR,
        SECURE_DIR,
        GENERATED_DIR,
        SELF_IMPROVEMENT_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
