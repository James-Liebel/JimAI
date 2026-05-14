"""Feedback aggregator — turn raw signals into learned user preferences.

The feedback API (api/feedback.py) writes append-only events. This module
consumes those events and derives durable signals the chat system can act on:

  - per-user style preferences (verbose/concise, formal/casual, bullets/prose,
    show-reasoning/just-answer) — derived by examining the SHAPE of responses
    the user thumbed up vs the corrections they wrote;
  - per-model accuracy (is qwen3:14b actually better than qwen3:8b for this
    user? — informs routing tweaks later);
  - a rolling "lessons learned" list — short imperatives like
    "this user prefers shorter intros" — folded into the cross_chat_memory
    preferences category so they reach the chat system prompt.

Aggregation is incremental: each feedback event triggers one
``incorporate_feedback_async`` call. We never re-scan the full log on the
hot path; the log is only re-scanned by the offline training builder.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

from config.settings import PROJECT_ROOT
from memory import cross_chat_memory, db

logger = logging.getLogger(__name__)

FEEDBACK_LOG = PROJECT_ROOT / "data" / "feedback.jsonl"
_PREFS_SLOT = "feedback_prefs"

# Style heuristics — light-weight, deterministic. We don't want a feedback loop
# that needs the model to interpret feedback before we can act on it.

_BULLET_LINE = re.compile(r"(?m)^\s*[-*•]\s")
_NUMBERED_LINE = re.compile(r"(?m)^\s*\d+[.)]\s")
_CODE_FENCE = re.compile(r"```")
_HEADING = re.compile(r"(?m)^#{1,3}\s")


def _shape(text: str) -> dict[str, Any]:
    """Cheap structural fingerprint of a response."""
    t = text or ""
    n = max(len(t), 1)
    return {
        "length": len(t),
        "bullet_density": len(_BULLET_LINE.findall(t)) / max(len(t.splitlines()), 1),
        "numbered_density": len(_NUMBERED_LINE.findall(t)) / max(len(t.splitlines()), 1),
        "code_fences": len(_CODE_FENCE.findall(t)) // 2,
        "headings": len(_HEADING.findall(t)),
        "paragraphs": t.count("\n\n") + 1,
        "questions": t.count("?"),
    }


def _read_prefs(user_id: str) -> dict[str, Any]:
    rec = db.read_user_slot(user_id, _PREFS_SLOT)
    if rec and isinstance(rec.get("data"), dict):
        return dict(rec["data"])
    return {
        "version": 1,
        "lessons": [],
        "thumbs_up_shape_sum": {},
        "thumbs_down_shape_sum": {},
        "thumbs_up_count": 0,
        "thumbs_down_count": 0,
        "model_scores": {},
        "updated_at": 0.0,
    }


def _write_prefs(user_id: str, data: dict[str, Any]) -> None:
    data["updated_at"] = time.time()
    db.write_user_slot(user_id, _PREFS_SLOT, data)


def _accumulate_shape(target: dict[str, float], shape: dict[str, Any]) -> None:
    for key, val in shape.items():
        try:
            target[key] = float(target.get(key, 0.0)) + float(val)
        except (TypeError, ValueError):
            continue


def _avg_shape(total: dict[str, float], count: int) -> dict[str, float]:
    if count <= 0:
        return {}
    return {k: round(float(v) / count, 3) for k, v in total.items()}


def _derive_lessons(prefs: dict[str, Any]) -> list[str]:
    """Translate quantitative style deltas into one-line imperative lessons.

    A lesson is generated only when the up-vs-down delta is materially large —
    we don't want to pollute the prompt with weak signals."""
    up = _avg_shape(prefs.get("thumbs_up_shape_sum") or {}, int(prefs.get("thumbs_up_count") or 0))
    down = _avg_shape(prefs.get("thumbs_down_shape_sum") or {}, int(prefs.get("thumbs_down_count") or 0))
    if not up or not down:
        return []
    lessons: list[str] = []

    # Length preference.
    if up.get("length", 0) and down.get("length", 0):
        ratio = up["length"] / max(down["length"], 1)
        if ratio < 0.7:
            lessons.append("This user prefers shorter answers — cut intros and rephrasings.")
        elif ratio > 1.4:
            lessons.append("This user prefers thorough answers — show reasoning steps and edge cases.")

    # Structure preference.
    up_struct = up.get("bullet_density", 0) + up.get("numbered_density", 0) + up.get("headings", 0)
    down_struct = down.get("bullet_density", 0) + down.get("numbered_density", 0) + down.get("headings", 0)
    if up_struct > down_struct + 0.3:
        lessons.append("This user prefers structured answers (bullets / numbered / headings).")
    elif down_struct > up_struct + 0.3:
        lessons.append("This user prefers prose — avoid heavy bullet/heading scaffolding unless asked.")

    # Code emphasis.
    if up.get("code_fences", 0) > down.get("code_fences", 0) + 0.5:
        lessons.append("This user prefers code-first answers when the question is technical.")

    return lessons


def _propagate_lessons_to_memory(user_id: str, lessons: list[str]) -> None:
    """Push the derived lessons into the categorized cross_chat_memory as
    preferences so they reach the chat system prompt. Bounded list — keep
    only the latest distinct lessons."""
    if not lessons:
        return
    try:
        # Read current categorized state.
        with cross_chat_memory._LOCK:
            data = cross_chat_memory._load(user_id)
            categories: dict[str, list[str]] = data.get("categories") or {}
            existing = list(categories.get("preferences") or [])
            seen: set[str] = set(p.strip() for p in existing if p.strip())
            for lesson in lessons:
                lesson = lesson.strip()
                if lesson and lesson not in seen:
                    existing.append(lesson)
                    seen.add(lesson)
            # Keep the most recent N preferences.
            categories["preferences"] = existing[-12:]
            data["categories"] = categories
            cross_chat_memory._save(user_id, data)
    except Exception:
        logger.debug("propagate_lessons_to_memory failed", exc_info=True)


async def incorporate_feedback_async(entry: dict) -> None:
    """Apply one feedback entry to the per-user preference state.

    Called fire-and-forget from the feedback API. Reads + writes a single
    user_memory slot so concurrent feedback events on different users don't
    contend. For the same user, the I/O is serialized by sqlite.
    """
    try:
        user_id = str(entry.get("user_id") or "default")
        prefs = _read_prefs(user_id)
        kind = entry.get("kind")

        if kind == "explicit":
            response = str(entry.get("response") or entry.get("bad_response") or "")
            if not response:
                return
            shape = _shape(response)
            if entry.get("thumbs_up"):
                _accumulate_shape(prefs["thumbs_up_shape_sum"], shape)
                prefs["thumbs_up_count"] = int(prefs.get("thumbs_up_count") or 0) + 1
                model = str(entry.get("model") or "")
                if model:
                    ms = prefs.setdefault("model_scores", {})
                    ms[model] = ms.get(model, 0) + 1
            elif entry.get("bad_response") or entry.get("correction"):
                _accumulate_shape(prefs["thumbs_down_shape_sum"], shape)
                prefs["thumbs_down_count"] = int(prefs.get("thumbs_down_count") or 0) + 1
                model = str(entry.get("model") or "")
                if model:
                    ms = prefs.setdefault("model_scores", {})
                    ms[model] = ms.get(model, 0) - 1
            # If a correction is present, the user has effectively SHOWN us
            # what they wanted — score the correction's shape as a strong
            # thumbs-up signal.
            correction = str(entry.get("correction") or "")
            if correction:
                _accumulate_shape(prefs["thumbs_up_shape_sum"], _shape(correction))
                prefs["thumbs_up_count"] = int(prefs.get("thumbs_up_count") or 0) + 1
        elif kind == "implicit":
            signal = entry.get("signal")
            prior_response = str(entry.get("prior_response") or "")
            if not prior_response:
                return
            shape = _shape(prior_response)
            if signal in {"rephrase", "abandon"}:
                # Same direction as thumbs-down but smaller weight: count as
                # 0.5 votes. We approximate this by only updating sums (not
                # the count), so the running average shifts but slowly.
                _accumulate_shape(prefs["thumbs_down_shape_sum"], shape)
            elif signal in {"copy", "follow_up_positive"}:
                _accumulate_shape(prefs["thumbs_up_shape_sum"], shape)

        # Re-derive lessons after each update — cheap, deterministic.
        lessons = _derive_lessons(prefs)
        prefs["lessons"] = lessons
        _write_prefs(user_id, prefs)

        if lessons:
            _propagate_lessons_to_memory(user_id, lessons)
    except Exception:
        logger.warning("incorporate_feedback_async failed", exc_info=True)


def get_lessons(user_id: str) -> list[str]:
    """Public read for chat.py to inject into the system prompt."""
    prefs = _read_prefs(user_id)
    return list(prefs.get("lessons") or [])


def get_model_scores(user_id: str) -> dict[str, int]:
    """Return per-model net feedback (positive minus negative) for this user.
    Used by routing tweaks to bias toward models the user has rated well."""
    prefs = _read_prefs(user_id)
    return dict(prefs.get("model_scores") or {})


# ── Implicit-signal detection helper (called from chat.py before answering) ──


def detect_implicit_signal(
    new_prompt: str,
    prior_user_message: str,
    prior_assistant_message: str,
) -> str | None:
    """Heuristic-only detection of implicit feedback the user just produced.

    Returns the signal name ("rephrase", "follow_up_positive", "abandon")
    or None if no signal is detected. Caller is responsible for logging.
    """
    p = (new_prompt or "").strip().lower()
    prior_q = (prior_user_message or "").strip().lower()
    if not p:
        return None

    # Strong positive: short acknowledgement.
    if len(p) <= 30 and re.search(
        r"\b(thanks|thank you|perfect|exactly|that works|got it|nice|nailed it|that's it|love it)\b",
        p,
    ):
        return "follow_up_positive"

    # Rephrase, strong form: explicit correction phrases trigger regardless of
    # token overlap with the prior question. These phrases are almost always
    # signaling "your last answer wasn't what I wanted".
    _CORRECTION_PHRASES = re.compile(
        r"\b(actually,?\s+i (meant|wanted|was asking)|i meant\b|no,?\s+i wanted|"
        r"try again|that's not (what|right)|that wasn't (what|right)|"
        r"redo|rewrite|that was wrong|incorrect|not what i (meant|wanted|asked)|"
        r"no,?\s+(i|that|the)|let me clarify)\b",
        re.IGNORECASE,
    )
    if _CORRECTION_PHRASES.search(p):
        return "rephrase"

    # Rephrase, soft form: token overlap with the prior question.
    if prior_q and len(p) > 12:
        prior_tokens = set(re.findall(r"[a-z0-9]{4,}", prior_q))
        new_tokens = set(re.findall(r"[a-z0-9]{4,}", p))
        if prior_tokens and len(prior_tokens & new_tokens) >= max(3, len(prior_tokens) // 3):
            # Heuristic: if the prior assistant response was long but the user
            # is asking a near-identical thing, treat as a soft rephrase.
            if len(prior_assistant_message or "") > 600 and (prior_tokens & new_tokens) and len(p) <= 80:
                return "rephrase"

    return None
