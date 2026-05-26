"""Persistent, user-editable coding knowledge for the self-improvement pipeline.

The self-improve coder and proposal generator read this file so generated changes
follow the project's real conventions instead of being invented from scratch — the
"give the agents a knowledge file" lever. Editable from the SelfCode UI via
GET/POST /api/agent-space/self-improve/knowledge.
"""

from __future__ import annotations

import logging

from .paths import SELF_IMPROVEMENT_DIR

logger = logging.getLogger(__name__)

KNOWLEDGE_FILE = SELF_IMPROVEMENT_DIR / "coding_knowledge.md"
MAX_KNOWLEDGE_CHARS = 8000

# Seeded on first read so the file is discoverable and immediately useful. Distilled
# from CLAUDE.md and .claude/rules; the user is expected to edit it for their project.
_DEFAULT_KNOWLEDGE = """# Coding Knowledge — Self-Improve

Conventions the self-improve agents must follow when changing this codebase. Edit
this file to teach the agents project-specific context; it is injected into the
coder and proposal prompts.

## Architecture
- Local-first: the backend talks ONLY to local Ollama. Never add cloud or API-key model providers.
- Backend: FastAPI (`backend/`). Frontend: React + Vite + Tailwind (`frontend/`). Desktop: Electron.
- Role prompts live in `backend/config/role_prompts.py`; model/speed tiers in `backend/config/models.py`.

## Python
- Typed, no bare `except`, `pathlib` over `os.path`. Group imports: stdlib, third-party, local.
- Prefer extending existing patterns over new abstractions. No dead code or commented-out blocks.
- Async tests use anyio (`@pytest.mark.anyio`), not pytest-asyncio.

## Frontend
- Tailwind only; no new UI libraries. Named exports, one component per file.
- Accessible: labels on inputs, visible focus, keyboard reachable.

## Safety
- Keep the app fully local: no telemetry, no cloud egress. Treat secrets and `.env` as untouchable.
- Make the smallest change that meets the objective; preserve existing behavior.
"""


def get_knowledge() -> str:
    """Return the saved coding knowledge, seeding the default file on first use."""
    try:
        if KNOWLEDGE_FILE.exists():
            return KNOWLEDGE_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read coding knowledge file: %s", exc)
        return ""
    return set_knowledge(_DEFAULT_KNOWLEDGE)


def set_knowledge(text: str) -> str:
    """Persist coding knowledge (capped at MAX_KNOWLEDGE_CHARS). Returns what was saved."""
    cleaned = (text or "").strip()[:MAX_KNOWLEDGE_CHARS]
    try:
        KNOWLEDGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        KNOWLEDGE_FILE.write_text(cleaned, encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write coding knowledge file: %s", exc)
    return cleaned


def knowledge_prompt_block(max_chars: int = MAX_KNOWLEDGE_CHARS) -> str:
    """Format the knowledge for injection into a role prompt, or "" if there is none."""
    text = get_knowledge().strip()
    if not text:
        return ""
    if len(text) > max_chars:
        text = text[: max_chars - 3] + "..."
    return (
        "PROJECT CODING KNOWLEDGE — follow these conventions; they override generic "
        "habits:\n" + text
    )
