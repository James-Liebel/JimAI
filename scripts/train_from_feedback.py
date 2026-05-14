"""Train a LoRA adapter on collected user feedback.

Two output modes from one input — data/feedback.jsonl:

  SFT pairs (default) — wherever the user provided a correction, treat the
  correction as the gold completion for the original prompt. Cleanly slots
  into the existing scripts/finetune.py runner.

  DPO pairs (``--dpo``) — emit {prompt, chosen, rejected} triples where chosen
  is the correction (or thumbs-up response) and rejected is the bad_response.
  This is what TRL's DPOTrainer consumes; the trainer is invoked here when
  ``--dpo --run`` is supplied.

Filters
-------
We drop:
  • thumbs-up entries without a captured response (nothing to learn from);
  • corrections shorter than 40 chars (likely throwaway);
  • entries where the bad_response and correction are near-identical
    (the user changed nothing — no preference signal).

Why this matters
----------------
The model that ships with JimAI is generic Qwen2.5. Real user feedback is
the only signal that teaches it *this user's* voice, depth preference, and
domain emphasis. Without this pipeline, feedback piles up in a JSONL and is
never consumed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _read_feedback(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    out: list[dict] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _near_identical(a: str, b: str) -> bool:
    """Cheap similarity: same length to ±5% and same first/last 40 chars."""
    a = (a or "").strip()
    b = (b or "").strip()
    if not a or not b:
        return False
    if abs(len(a) - len(b)) > max(40, len(a) // 20):
        return False
    return a[:40] == b[:40] and a[-40:] == b[-40:]


def build_sft_pairs(entries: list[dict]) -> list[dict]:
    """Each kept entry becomes one {prompt, completion} row.

    Priority order for the completion: explicit correction > thumbs_up response.
    Entries with neither are dropped — there's nothing for the model to imitate.
    """
    rows: list[dict] = []
    seen: set[str] = set()
    for e in entries:
        prompt = str(e.get("prompt") or "").strip()
        if not prompt:
            continue
        correction = str(e.get("correction") or "").strip()
        response = str(e.get("response") or "").strip()
        is_up = bool(e.get("thumbs_up"))
        completion = ""
        if correction and len(correction) >= 40:
            completion = correction
        elif is_up and response and len(response) >= 60:
            completion = response
        if not completion:
            continue
        key = hashlib.sha1(prompt.encode("utf-8", "replace")).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        rows.append({"prompt": prompt, "completion": completion})
    return rows


def build_dpo_pairs(entries: list[dict]) -> list[dict]:
    """Emit {prompt, chosen, rejected} for every correction-bearing entry.

    Chosen = correction (gold). Rejected = bad_response (what the model
    actually produced). Skipped when the two are near-identical.
    """
    rows: list[dict] = []
    seen: set[str] = set()
    for e in entries:
        prompt = str(e.get("prompt") or "").strip()
        correction = str(e.get("correction") or "").strip()
        bad = str(e.get("bad_response") or e.get("response") or "").strip()
        if not (prompt and correction and bad):
            continue
        if len(correction) < 40:
            continue
        if _near_identical(correction, bad):
            continue
        key = hashlib.sha1(prompt.encode("utf-8", "replace")).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        rows.append({"prompt": prompt, "chosen": correction, "rejected": bad})
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    p = argparse.ArgumentParser(description="Train (or just export) from JimAI feedback.")
    p.add_argument("--log", default="data/feedback.jsonl",
                   help="Feedback log path (default: data/feedback.jsonl).")
    p.add_argument("--out", default=None,
                   help="Output JSONL path. Defaults under data/corpus/.")
    p.add_argument("--dpo", action="store_true",
                   help="Emit DPO preference pairs (chosen/rejected) instead of SFT pairs.")
    p.add_argument("--run", action="store_true",
                   help="After building the corpus, run the trainer. Without this, "
                        "just write the JSONL and print the next command.")
    p.add_argument("--base", default="unsloth/Qwen2.5-7B-Instruct-bnb-4bit",
                   help="Base model for fine-tuning (passed to finetune.py).")
    p.add_argument("--min-pairs", type=int, default=8,
                   help="Refuse to write the corpus if fewer than this many pairs exist.")
    args = p.parse_args()

    log_path = Path(args.log)
    entries = _read_feedback(log_path)
    if not entries:
        print(f"No feedback found at {log_path}", file=sys.stderr)
        sys.exit(1)

    if args.dpo:
        rows = build_dpo_pairs(entries)
        out = Path(args.out) if args.out else Path("data/corpus/feedback_dpo.jsonl")
    else:
        rows = build_sft_pairs(entries)
        out = Path(args.out) if args.out else Path("data/corpus/feedback_sft.jsonl")

    if len(rows) < args.min_pairs:
        print(f"Only {len(rows)} usable pairs in feedback log (need {args.min_pairs}). "
              f"Collect more feedback before training.", file=sys.stderr)
        sys.exit(2)

    write_jsonl(out, rows)
    print(f"Wrote {len(rows)} {'DPO' if args.dpo else 'SFT'} pairs to {out}")

    if not args.run:
        if args.dpo:
            print()
            print("To run DPO training, install TRL with DPO support and invoke:")
            print(f"  python -m trl dpo --model_name_or_path {args.base} \\")
            print(f"      --dataset_name {out} --output_dir data/finetune/dpo \\")
            print("      --num_train_epochs 1 --per_device_train_batch_size 2 --learning_rate 5e-7")
        else:
            print()
            print("Next:")
            print(f"  python scripts/finetune.py --corpus {out}")
        return

    if args.dpo:
        # Run TRL DPO via its CLI when available.
        import subprocess
        cmd = [
            sys.executable, "-m", "trl", "dpo",
            "--model_name_or_path", args.base,
            "--dataset_name", str(out),
            "--output_dir", "data/finetune/dpo",
            "--num_train_epochs", "1",
            "--per_device_train_batch_size", "2",
            "--learning_rate", "5e-7",
        ]
        print("Running:", " ".join(cmd))
        sys.exit(subprocess.call(cmd))

    # SFT path — defer to the existing trainer so the LoRA-adapter machinery
    # stays in one place.
    import subprocess
    cmd = [sys.executable, "scripts/finetune.py", "--corpus", str(out), "--base", args.base]
    print("Running:", " ".join(cmd))
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
