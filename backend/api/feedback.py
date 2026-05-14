"""Feedback API — collects explicit and implicit signals for continuous learning.

Two intake channels:

  POST /api/feedback           — explicit (thumbs up/down + optional correction)
  POST /api/feedback/implicit  — implicit (user rephrased / abandoned / etc.)

Every recorded entry is fanned out three ways:

  1. Append-only JSONL log (data/feedback.jsonl) — durable, replay-able.
  2. Aggregate stats (data/feedback_stats.json) — UI display, training readiness.
  3. Live update: when the entry references a known chat turn, the
     corresponding chunk in ChromaDB gets its ``feedback_score`` metadata
     updated so retrieval can weight high-quality chunks higher (and
     suppress thumbed-down ones) on subsequent turns.

The training-readiness counter ``since_last_train`` is what drives the
auto-train trigger surfaced at /api/feedback/training_readiness.
"""

import asyncio
import json
import logging
import time
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/feedback", tags=["feedback"])

FEEDBACK_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "feedback.jsonl"
STATS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "feedback_stats.json"
TRAINING_THRESHOLD = 25  # number of new feedback entries before training is "ready"


class FeedbackRequest(BaseModel):
    prompt: str
    bad_response: str = ""
    correction: str = ""
    note: str = ""
    mode: str = "chat"
    session_id: str = "default"
    thumbs_up: bool = False
    # New fields (all optional so existing clients keep working).
    user_id: str = "default"
    message_id: str = ""            # client-assigned id of the assistant message
    response: str = ""              # the actual assistant text being rated
    model: str = ""                 # which model generated it (for per-model scoring)


class ImplicitFeedbackRequest(BaseModel):
    """Implicit signals — things the user did, not what they explicitly said."""
    signal: str                     # "rephrase" | "abandon" | "copy" | "follow_up_positive"
    user_id: str = "default"
    session_id: str = "default"
    prior_message_id: str = ""
    prior_response: str = ""
    new_prompt: str = ""            # for "rephrase" — the rewritten question


def _load_stats() -> dict:
    if STATS_PATH.exists():
        try:
            return json.loads(STATS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "total": 0,
        "since_last_train": 0,
        "by_mode": {},
        "by_signal": {},
        "thumbs_up": 0,
        "thumbs_down": 0,
        "corrections": 0,
        "last_train_date": "",
    }


def _save_stats(stats: dict) -> None:
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATS_PATH.write_text(json.dumps(stats, indent=2), encoding="utf-8")


def _append_log(entry: dict) -> None:
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FEEDBACK_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def _tag_vectordb_with_feedback(entry: dict) -> None:
    """When feedback references a specific message OR contains the response
    text, find the corresponding chunks in ChromaDB and stamp a feedback_score
    on the metadata. RAG retrieval at chat time uses this to prefer (or
    suppress) chunks tied to that turn.

    Matching is layered:
      1. message_id (if the frontend supplied one);
      2. response_hash (sha1 of the assistant response — works for any client
         that echoes the response text back in feedback).
    """
    try:
        import hashlib

        from memory import vectordb

        delta = 0.0
        if entry.get("thumbs_up"):
            delta = 1.0
        elif entry.get("bad_response") or entry.get("signal") in {"abandon", "rephrase"}:
            delta = -1.0
        elif entry.get("signal") in {"copy", "follow_up_positive"}:
            delta = 0.5
        if delta == 0.0:
            return

        msg_id = str(entry.get("message_id") or "").strip()
        if msg_id:
            await vectordb.adjust_metadata(
                where={"message_id": {"$eq": msg_id}},
                delta_field="feedback_score",
                delta_value=delta,
            )
            return

        # Fall back to response-hash matching.
        response_text = str(entry.get("response") or entry.get("bad_response") or entry.get("prior_response") or "")
        if not response_text:
            return
        rh = hashlib.sha1(response_text.encode("utf-8", "replace")).hexdigest()[:24]
        await vectordb.adjust_metadata(
            where={"response_hash": {"$eq": rh}},
            delta_field="feedback_score",
            delta_value=delta,
        )
    except Exception:
        logger.debug("vectordb feedback tagging skipped", exc_info=True)


@router.post("")
async def submit_feedback(req: FeedbackRequest) -> dict:
    """Record an explicit feedback entry."""
    entry = {
        "kind": "explicit",
        "user_id": req.user_id,
        "session_id": req.session_id,
        "message_id": req.message_id,
        "prompt": req.prompt,
        "response": req.response,
        "bad_response": req.bad_response,
        "correction": req.correction,
        "note": req.note,
        "mode": req.mode,
        "thumbs_up": req.thumbs_up,
        "model": req.model,
        "timestamp": time.time(),
    }
    _append_log(entry)

    stats = _load_stats()
    stats["total"] += 1
    stats["since_last_train"] += 1
    stats["by_mode"][req.mode] = stats["by_mode"].get(req.mode, 0) + 1
    if req.thumbs_up:
        stats["thumbs_up"] = stats.get("thumbs_up", 0) + 1
    elif req.bad_response or req.correction:
        stats["thumbs_down"] = stats.get("thumbs_down", 0) + 1
    if req.correction:
        stats["corrections"] = stats.get("corrections", 0) + 1
    _save_stats(stats)

    # Update live influences (vectordb tag + cross-chat preferences) without
    # blocking the HTTP response.
    try:
        loop = asyncio.get_running_loop()
        from agent_space.background_tasks import spawn
        spawn(_tag_vectordb_with_feedback(entry), name="feedback_tag_vectordb")
        from agents.feedback_loop import incorporate_feedback_async
        spawn(incorporate_feedback_async(entry), name="feedback_aggregate")
    except RuntimeError:
        pass

    logger.info("Feedback recorded (mode=%s, thumbs_up=%s, has_correction=%s)",
                req.mode, req.thumbs_up, bool(req.correction))
    return {"success": True, "total_feedback": stats["total"]}


@router.post("/implicit")
async def submit_implicit_feedback(req: ImplicitFeedbackRequest) -> dict:
    """Record an implicit signal: rephrase / abandon / copy / follow-up positive.

    These are noisier than thumbs but far more abundant. They feed the same
    aggregation pipeline as explicit feedback, just with smaller weight.
    """
    entry = {
        "kind": "implicit",
        "user_id": req.user_id,
        "session_id": req.session_id,
        "message_id": req.prior_message_id,
        "signal": req.signal,
        "prior_response": req.prior_response,
        "new_prompt": req.new_prompt,
        "timestamp": time.time(),
    }
    _append_log(entry)

    stats = _load_stats()
    stats["total"] += 1
    stats["since_last_train"] += 1
    stats["by_signal"][req.signal] = stats["by_signal"].get(req.signal, 0) + 1
    _save_stats(stats)

    try:
        loop = asyncio.get_running_loop()
        from agent_space.background_tasks import spawn
        spawn(_tag_vectordb_with_feedback(entry), name="feedback_implicit_tag")
        from agents.feedback_loop import incorporate_feedback_async
        spawn(incorporate_feedback_async(entry), name="feedback_implicit_aggregate")
    except RuntimeError:
        pass

    return {"success": True, "signal": req.signal}


@router.get("/stats")
async def get_stats() -> dict:
    """Return feedback statistics (UI display)."""
    return _load_stats()


@router.get("/training_readiness")
async def training_readiness() -> dict:
    """Tell the UI whether enough feedback has accumulated to warrant a
    retraining cycle. The threshold is intentionally conservative — too many
    auto-train cycles is worse than too few, because each cycle costs GPU time
    and risks catastrophic forgetting if the new data is noisy.
    """
    stats = _load_stats()
    since = int(stats.get("since_last_train") or 0)
    return {
        "since_last_train": since,
        "threshold": TRAINING_THRESHOLD,
        "ready": since >= TRAINING_THRESHOLD,
        "thumbs_up": int(stats.get("thumbs_up") or 0),
        "thumbs_down": int(stats.get("thumbs_down") or 0),
        "corrections": int(stats.get("corrections") or 0),
    }


@router.post("/mark_trained")
async def mark_trained() -> dict:
    """Reset the since_last_train counter after a training run completes."""
    stats = _load_stats()
    stats["since_last_train"] = 0
    stats["last_train_date"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _save_stats(stats)
    return {"success": True, "last_train_date": stats["last_train_date"]}
