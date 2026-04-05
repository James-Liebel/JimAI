"""Cross-chat memory: durable bullet list merged from many conversations (local file, not model weights)."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from config.settings import PROJECT_ROOT

logger = logging.getLogger(__name__)

_PATH = PROJECT_ROOT / "data" / "memory" / "cross_chat_memory.json"
_LOCK = threading.Lock()
_DEFAULT: dict[str, Any] = {"bullets": [], "updated_at": 0.0, "version": 1}

_MAX_BULLETS = 28
_PENDING_MERGE_THRESHOLD = 5


def _load() -> dict[str, Any]:
    if not _PATH.exists():
        return dict(_DEFAULT)
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return dict(_DEFAULT)
        bullets = data.get("bullets")
        if not isinstance(bullets, list):
            bullets = []
        return {
            "bullets": [str(b).strip() for b in bullets if str(b).strip()][: _MAX_BULLETS + 10],
            "updated_at": float(data.get("updated_at") or 0),
            "version": int(data.get("version") or 1),
            "pending": list(data.get("pending") or []) if isinstance(data.get("pending"), list) else [],
        }
    except Exception:
        logger.warning("cross_chat_memory: failed to load, resetting", exc_info=True)
        return dict(_DEFAULT)


def _save(data: dict[str, Any]) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "bullets": data.get("bullets", [])[:_MAX_BULLETS],
        "updated_at": time.time(),
        "version": int(data.get("version") or 1),
        "pending": data.get("pending") or [],
    }
    _PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")


def get_prompt_block(max_bullets: int = 12) -> str:
    """Short block for system prompt (empty if nothing stored)."""
    with _LOCK:
        data = _load()
    bullets = [b for b in data.get("bullets", []) if b][:max_bullets]
    if not bullets:
        return ""
    lines = "\n".join(f"- {b}" for b in bullets)
    return (
        "Cross-chat notes (learned from prior conversations in this app; approximate—verify with the user):\n"
        f"{lines}"
    )


def append_pending(note: str) -> None:
    """Queue a short note; triggers async consolidation when enough pending."""
    note = (note or "").strip()
    if not note or len(note) > 1200:
        return
    with _LOCK:
        data = _load()
        pending = list(data.get("pending") or [])
        pending.append(note[:1200])
        data["pending"] = pending[-20:]
        _save(data)
    if len(pending) >= _PENDING_MERGE_THRESHOLD:
        try:
            import asyncio

            asyncio.get_running_loop().create_task(consolidate_pending())
        except RuntimeError:
            pass


async def consolidate_pending() -> None:
    """Merge pending notes + existing bullets with a small local model."""
    from models import ollama_client
    from models.router import get_model_config

    with _LOCK:
        data = _load()
        pending = list(data.get("pending") or [])
        bullets = list(data.get("bullets") or [])
        if not pending and not bullets:
            return
        data["pending"] = []
        _save(data)

    cfg = get_model_config("chat")
    model = cfg.model
    payload = {
        "existing_bullets": bullets[:_MAX_BULLETS],
        "new_notes": pending,
    }
    prompt = (
        "You maintain a concise memory across many user chats. "
        "Given existing bullets and new notes, output STRICT JSON only: "
        '{"bullets": ["...", ...]} with at most '
        f"{_MAX_BULLETS} bullets. Each bullet is one short fact, preference, recurring topic, "
        "or project name—no duplicates, no chat IDs, no speculation.\n\n"
        f"Input JSON:\n{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        text = await ollama_client.generate_full(
            model=model,
            prompt=prompt,
            system="Return valid JSON only.",
            temperature=0.15,
        )
        raw = text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(raw)
        merged = parsed.get("bullets") if isinstance(parsed, dict) else None
        if not isinstance(merged, list):
            return
        clean = [str(b).strip() for b in merged if str(b).strip()][: _MAX_BULLETS]
        with _LOCK:
            data = _load()
            data["bullets"] = clean
            data["pending"] = []
            _save(data)
        logger.info("cross_chat_memory: consolidated to %d bullets", len(clean))
    except Exception:
        logger.warning("cross_chat_memory: consolidate failed", exc_info=True)
        with _LOCK:
            data = _load()
            data["pending"] = pending + (data.get("pending") or [])
            _save(data)
