"""Build SFT and DPO training data from JimAI's own history.

Two signals feed the trainer:

- **SFT** (supervised fine-tuning): every user→assistant turn in chat history
  becomes a chat example, tagged with the message ``mode`` so it can be routed
  to the model that serves that role.
- **DPO** (preference): the self-improve pipeline already labels proposed diffs
  ``approved``/``applied`` vs ``rejected``. Grouping by ``run_id`` yields
  chosen/rejected pairs for the same objective — exactly the shape DPO wants.

The pure transform functions accept their inputs directly (so they are unit
testable without the encrypted DB); the zero-arg wrappers load from the live
stores. Heavy store imports are deferred into the loaders to keep import cheap.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

# Roles whose system prompt should be attached to an SFT example, keyed by the
# message `mode` column. Unknown modes fall back to the chat role.
_DEFAULT_ROLE = "chat"

SFTExample = dict[str, Any]   # {"messages": [{"role","content"}...], "mode": str}
DPOPair = dict[str, str]      # {"prompt", "chosen", "rejected"}


# ── SFT ───────────────────────────────────────────────────────────────────

def _system_for(mode: str | None) -> str:
    from config.models import get_configs

    role = mode if mode else _DEFAULT_ROLE
    configs = get_configs()
    cfg = configs.get(role) or configs.get(_DEFAULT_ROLE)
    return cfg.system_prompt if cfg else ""


def transcripts_to_sft(transcripts: Iterable[list[dict[str, Any]]]) -> list[SFTExample]:
    """Turn chat transcripts into SFT chat examples (each user→assistant turn)."""
    examples: list[SFTExample] = []
    for transcript in transcripts:
        turns = [
            msg
            for msg in transcript
            if msg.get("role") in {"user", "assistant"}
            and str(msg.get("content") or "").strip()
        ]
        for current, following in zip(turns, turns[1:]):
            if current["role"] != "user" or following["role"] != "assistant":
                continue
            mode = str(following.get("mode") or current.get("mode") or _DEFAULT_ROLE)
            messages: list[dict[str, str]] = []
            system = _system_for(mode)
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": str(current["content"])})
            messages.append({"role": "assistant", "content": str(following["content"])})
            examples.append({"messages": messages, "mode": mode})
    return examples


def _load_all_transcripts() -> list[list[dict[str, Any]]]:
    from memory.db import list_chats_rows, load_chat_row

    transcripts: list[list[dict[str, Any]]] = []
    for chat in list_chats_rows(limit=5000):
        chat_id = str(chat.get("id") or "")
        if not chat_id:
            continue
        row = load_chat_row(chat_id)
        if row and isinstance(row.get("messages"), list):
            transcripts.append(row["messages"])
    return transcripts


def build_sft_examples() -> list[SFTExample]:
    """All SFT examples mined from chat history."""
    return transcripts_to_sft(_load_all_transcripts())


# ── DPO ───────────────────────────────────────────────────────────────────

_CHOSEN_STATUSES = {"approved", "applied"}
_REJECTED_STATUS = "rejected"


def _review_text(review: dict[str, Any]) -> str:
    diff = str(review.get("diff") or "").strip()
    if diff:
        return diff
    summary = review.get("summary")
    return json.dumps(summary, indent=2) if summary else str(review.get("objective") or "")


def reviews_to_dpo(reviews: Iterable[dict[str, Any]]) -> list[DPOPair]:
    """Pair approved vs rejected proposals of the same run into DPO examples."""
    chosen_by_run: dict[str, list[dict[str, Any]]] = {}
    rejected_by_run: dict[str, list[dict[str, Any]]] = {}
    for review in reviews:
        run_id = str(review.get("run_id") or "")
        if not run_id:
            continue
        status = str(review.get("status") or "")
        if status in _CHOSEN_STATUSES:
            chosen_by_run.setdefault(run_id, []).append(review)
        elif status == _REJECTED_STATUS:
            rejected_by_run.setdefault(run_id, []).append(review)

    pairs: list[DPOPair] = []
    for run_id, chosen in chosen_by_run.items():
        rejected = rejected_by_run.get(run_id)
        if not rejected:
            continue
        pairs.append(
            {
                "prompt": str(chosen[0].get("objective") or ""),
                "chosen": _review_text(chosen[0]),
                "rejected": _review_text(rejected[0]),
            }
        )
    return pairs


def build_dpo_pairs() -> list[DPOPair]:
    """All DPO pairs mined from the review store's accept/reject verdicts."""
    from agent_space.review_store import ReviewStore

    return reviews_to_dpo(ReviewStore().list_reviews(limit=5000))


# ── IO ────────────────────────────────────────────────────────────────────

def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    """Write rows as JSONL, creating parent dirs. Returns the row count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file into rows. A missing file yields no rows."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def load_external_sft(sources_dir: Path) -> list[SFTExample]:
    """Load every fetched external SFT file (``*.jsonl``) from a sources dir.

    ``training.run fetch`` writes role-tagged instruction data here; merging it
    with the locally mined examples is what lets external and self-generated data
    train through one path. Files load in filename order; a missing dir is empty.
    """
    if not sources_dir.is_dir():
        return []
    examples: list[SFTExample] = []
    for path in sorted(sources_dir.glob("*.jsonl")):
        examples.extend(read_jsonl(path))
    return examples
