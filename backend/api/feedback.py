"""Feedback API — collects thumbs up/down + corrections for continuous learning."""

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


class FeedbackRequest(BaseModel):
    prompt: str
    bad_response: str = ""
    correction: str = ""
    note: str = ""
    mode: str = "chat"
    session_id: str = "default"
    thumbs_up: bool = False


def _load_stats() -> dict:
    if STATS_PATH.exists():
        return json.loads(STATS_PATH.read_text(encoding="utf-8"))
    return {"total": 0, "since_last_train": 0, "by_mode": {}, "last_train_date": ""}


def _save_stats(stats: dict) -> None:
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATS_PATH.write_text(json.dumps(stats, indent=2), encoding="utf-8")


@router.post("")
async def submit_feedback(req: FeedbackRequest) -> dict:
    """Record a feedback entry (thumbs up/down + optional correction)."""
    entry = {
        "prompt": req.prompt,
        "bad_response": req.bad_response,
        "correction": req.correction,
        "note": req.note,
        "mode": req.mode,
        "session_id": req.session_id,
        "thumbs_up": req.thumbs_up,
        "timestamp": time.time(),
    }

    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FEEDBACK_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    # Update running stats
    stats = _load_stats()
    stats["total"] += 1
    stats["since_last_train"] += 1
    stats["by_mode"][req.mode] = stats["by_mode"].get(req.mode, 0) + 1
    _save_stats(stats)

    logger.info("Feedback recorded (mode=%s, thumbs_up=%s)", req.mode, req.thumbs_up)
    return {"success": True, "total_feedback": stats["total"]}


@router.get("/stats")
async def get_stats() -> dict:
    """Return feedback statistics."""
    return _load_stats()
