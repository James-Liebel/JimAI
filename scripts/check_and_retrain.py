"""Check if enough feedback has accumulated to trigger re-training."""

import json
import subprocess
import sys
import time
from pathlib import Path


def main():
    feedback_path = Path("data/feedback.jsonl")
    last_train_path = Path("data/last_train.json")
    corpus_path = Path("data/corpus/training.jsonl")
    threshold = 200

    if not feedback_path.exists():
        print("No feedback file found. Nothing to do.")
        sys.exit(0)

    # Count feedback entries
    with open(feedback_path, "r", encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]
    current_count = len(entries)

    # Load last training info
    if last_train_path.exists():
        last_train = json.loads(last_train_path.read_text(encoding="utf-8"))
        count_at_last_train = last_train.get("count_at_last_train", 0)
        last_date = last_train.get("date", "never")
    else:
        count_at_last_train = 0
        last_date = "never"

    new_entries = current_count - count_at_last_train

    print(f"Total feedback entries: {current_count}")
    print(f"Since last training: {new_entries}")
    print(f"Last training date: {last_date}")
    print(f"Threshold: {threshold}")
    print()

    if new_entries >= threshold:
        print(f"Triggering fine-tune with {new_entries} new samples...")

        # Convert corrections to training pairs
        corpus_path.parent.mkdir(parents=True, exist_ok=True)
        with open(corpus_path, "a", encoding="utf-8") as out:
            for entry in entries[count_at_last_train:]:
                if entry.get("correction"):
                    pair = {
                        "prompt": entry["prompt"],
                        "completion": entry["correction"],
                    }
                    out.write(json.dumps(pair) + "\n")

        # Run fine-tuning
        result = subprocess.run(
            [sys.executable, "scripts/finetune.py"],
            capture_output=True,
            text=True,
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"Fine-tuning failed:\n{result.stderr}")
            sys.exit(1)

        # Update last_train.json
        last_train_path.write_text(
            json.dumps({
                "count_at_last_train": current_count,
                "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            }, indent=2),
            encoding="utf-8",
        )
        print("Training complete. last_train.json updated.")
    else:
        remaining = threshold - new_entries
        print(f"Not enough feedback yet: need {remaining} more entries")


if __name__ == "__main__":
    main()
