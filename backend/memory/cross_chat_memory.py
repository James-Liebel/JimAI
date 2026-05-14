"""Cross-chat memory: per-user durable bullet list merged from many conversations.

Storage moved from a single global JSON file to the SQLite user_memory table so
different users can learn different things. The legacy JSON file (if present)
is imported once into the default user's slot on first access.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from config.settings import PROJECT_ROOT

from . import db

logger = logging.getLogger(__name__)

_LEGACY_PATH = PROJECT_ROOT / "data" / "memory" / "cross_chat_memory.json"
_LOCK = threading.Lock()
_SLOT = "cross_chat_memory"

_MAX_BULLETS = 28
_PENDING_MERGE_THRESHOLD = 5

_DEFAULT: dict[str, Any] = {"bullets": [], "pending": [], "updated_at": 0.0, "version": 1}
_LEGACY_IMPORTED = False


def _legacy_import_once() -> None:
    global _LEGACY_IMPORTED
    if _LEGACY_IMPORTED:
        return
    _LEGACY_IMPORTED = True
    try:
        if not _LEGACY_PATH.exists():
            return
        existing = db.read_user_slot(db.DEFAULT_USER_ID, _SLOT)
        if existing is not None:
            return
        raw = json.loads(_LEGACY_PATH.read_text(encoding="utf-8"))
        bullets = [str(b).strip() for b in (raw.get("bullets") or []) if str(b).strip()]
        pending = [str(p).strip() for p in (raw.get("pending") or []) if str(p).strip()]
        db.write_user_slot(
            db.DEFAULT_USER_ID,
            _SLOT,
            {
                "bullets": bullets[:_MAX_BULLETS],
                "pending": pending[-20:],
                "version": int(raw.get("version") or 1),
            },
        )
        logger.info("cross_chat_memory: migrated legacy JSON for user '%s'", db.DEFAULT_USER_ID)
    except Exception:
        logger.warning("cross_chat_memory: legacy JSON migration failed", exc_info=True)


def _load(user_id: str) -> dict[str, Any]:
    _legacy_import_once()
    rec = db.read_user_slot(user_id, _SLOT)
    if rec is None or not isinstance(rec.get("data"), dict):
        return dict(_DEFAULT)
    data = rec["data"]
    cats_in = data.get("categories")
    categories: dict[str, list[str]] = {}
    if isinstance(cats_in, dict):
        for k, v in cats_in.items():
            if isinstance(v, list):
                categories[str(k)] = [str(x).strip() for x in v if str(x).strip()][:_MAX_BULLETS]
    return {
        "bullets": [str(b).strip() for b in (data.get("bullets") or []) if str(b).strip()][: _MAX_BULLETS + 10],
        "pending": [str(p).strip() for p in (data.get("pending") or []) if str(p).strip()],
        "categories": categories,
        "updated_at": float(rec.get("updated_at") or 0),
        "version": int(data.get("version") or 1),
    }


def _save(user_id: str, data: dict[str, Any]) -> None:
    payload = {
        "bullets": list(data.get("bullets") or [])[:_MAX_BULLETS],
        "pending": list(data.get("pending") or [])[-20:],
        "categories": dict(data.get("categories") or {}),
        "version": int(data.get("version") or 1),
    }
    db.write_user_slot(user_id, _SLOT, payload)


_CATEGORY_HEADERS: dict[str, str] = {
    "user_facts": "About the user (identity, role, stated facts)",
    "projects": "Active projects",
    "preferences": "Preferences and working style",
    "open_threads": "Open threads and unfinished work",
}


def get_prompt_block(max_bullets: int = 12, user_id: str = db.DEFAULT_USER_ID) -> str:
    """Short block for system prompt (empty if nothing stored for this user).

    Renders categorized bullets when available (the LLM consolidator returns
    a categorized dict); falls back to the flat bullet list for legacy data.
    """
    with _LOCK:
        data = _load(user_id)
    categories = data.get("categories") if isinstance(data.get("categories"), dict) else None
    if categories and any(categories.values()):
        sections: list[str] = []
        for key, header in _CATEGORY_HEADERS.items():
            items = [str(x).strip() for x in (categories.get(key) or []) if str(x).strip()]
            if not items:
                continue
            sections.append(f"### {header}\n" + "\n".join(f"- {x}" for x in items[:max_bullets]))
        if sections:
            return (
                "## What you know about this user (verify before relying on any line)\n"
                + "\n\n".join(sections)
            )
    bullets = [b for b in data.get("bullets", []) if b][:max_bullets]
    if not bullets:
        return ""
    lines = "\n".join(f"- {b}" for b in bullets)
    return (
        "Cross-chat notes (learned from this user's prior conversations; approximate—verify with the user):\n"
        f"{lines}"
    )


def append_pending(note: str, user_id: str = db.DEFAULT_USER_ID) -> None:
    """Queue a short note; triggers async consolidation when enough pending."""
    note = (note or "").strip()
    if not note or len(note) > 1200:
        return
    with _LOCK:
        data = _load(user_id)
        pending = list(data.get("pending") or [])
        pending.append(note[:1200])
        data["pending"] = pending[-20:]
        _save(user_id, data)
    if len(pending) >= _PENDING_MERGE_THRESHOLD:
        try:
            import asyncio
            asyncio.get_running_loop()
            from agent_space.background_tasks import spawn
            spawn(consolidate_pending(user_id=user_id), name=f"cross_chat_consolidate:{user_id}")
        except RuntimeError:
            pass


async def consolidate_pending(user_id: str = db.DEFAULT_USER_ID) -> None:
    """Merge pending notes + existing bullets with a small local model."""
    from models import ollama_client
    from models.router import get_model_config

    with _LOCK:
        data = _load(user_id)
        pending = list(data.get("pending") or [])
        bullets = list(data.get("bullets") or [])
        if not pending and not bullets:
            return
        data["pending"] = []
        _save(user_id, data)

    cfg = get_model_config("chat")
    model = cfg.model
    # Carry forward the prior categorized state if present so the consolidator
    # can update it incrementally instead of starting from scratch each time.
    prior_categories = data.get("categories") if isinstance(data.get("categories"), dict) else {}
    payload = {
        "existing_categories": {
            k: list(prior_categories.get(k) or [])[:_MAX_BULLETS]
            for k in _CATEGORY_HEADERS.keys()
        },
        "legacy_flat_bullets": bullets[:_MAX_BULLETS],
        "new_notes": pending,
    }
    prompt = (
        "You maintain durable memory about ONE specific user across many chats.\n"
        "Read the new notes plus the prior categorized memory and output STRICT JSON only.\n\n"
        "Output schema (every key required, lists may be empty):\n"
        "{\n"
        '  "user_facts":   ["who they are / role / stated facts about themselves"],\n'
        '  "projects":     ["named ongoing projects with one-line scope"],\n'
        '  "preferences":  ["how they like to work / styles / constraints"],\n'
        '  "open_threads": ["unresolved tasks or questions still pending"]\n'
        "}\n\n"
        "Rules:\n"
        f"- Each list at most {_MAX_BULLETS} items.\n"
        "- One short bullet per item. No chat IDs. No speculation.\n"
        "- Drop duplicates and obvious noise (e.g. vocabulary lists from unrelated chats).\n"
        "- When a project's open threads are resolved, remove them from open_threads.\n"
        "- Prefer specific to generic: 'Building atlas browser agent in Electron' beats 'works on AI'.\n\n"
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
        if not isinstance(parsed, dict):
            return
        cleaned: dict[str, list[str]] = {}
        for key in _CATEGORY_HEADERS.keys():
            val = parsed.get(key)
            if isinstance(val, list):
                cleaned[key] = [str(b).strip() for b in val if str(b).strip()][:_MAX_BULLETS]
        # Backward-compat flat list — flatten categories so legacy consumers still work.
        flat: list[str] = []
        for k in _CATEGORY_HEADERS.keys():
            flat.extend(cleaned.get(k, []))
        flat = flat[:_MAX_BULLETS]
        with _LOCK:
            data = _load(user_id)
            data["categories"] = cleaned
            data["bullets"] = flat
            data["pending"] = []
            _save(user_id, data)
        logger.info(
            "cross_chat_memory: consolidated for user '%s' — facts=%d projects=%d prefs=%d threads=%d",
            user_id, len(cleaned.get("user_facts", [])), len(cleaned.get("projects", [])),
            len(cleaned.get("preferences", [])), len(cleaned.get("open_threads", [])),
        )
    except Exception:
        logger.warning("cross_chat_memory: consolidate failed", exc_info=True)
        with _LOCK:
            data = _load(user_id)
            data["pending"] = pending + (data.get("pending") or [])
            _save(user_id, data)
