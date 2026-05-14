"""Build a training corpus for JimAI's fine-tune pipeline.

Two source modes are supported:

  --from-chats          Harvest (user_message, assistant_message) pairs from
                        data/chats/*.json. Filters out very short turns and
                        de-duplicates near-identical user prompts. This is
                        the primary mode — it teaches the adapter the user's
                        actual question style and the assistant's preferred
                        answer shape.

  --from-docs <dir>     Walk a directory of .txt/.md/.pdf/.docx files and
                        generate (synthesized-question, passage) pairs. Used
                        to bake domain knowledge in.

The two modes can be combined: pass both flags to get a mixed corpus. The
output is a single JSONL file at --output (default data/corpus/training.jsonl)
with one {"prompt": ..., "completion": ...} per line — what scripts/finetune.py
consumes.

Quality filters
---------------
We aggressively drop low-quality rows: empty turns, model error messages,
extremely long pastes (>4000 chars in the user message often means the user
pasted code rather than asked a question), and turns where the assistant
hedged with "I can't help with that" or similar refusals. These would teach
the adapter exactly the wrong behaviour.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


OLLAMA_URL = "http://localhost:11434"

# Quality filters for chat pairs.
_MIN_USER_LEN = 12
_MIN_ASSISTANT_LEN = 80
_MAX_USER_LEN = 4000
_MAX_ASSISTANT_LEN = 8000

_REFUSAL_HINTS = re.compile(
    r"(?:i (?:can'?t|cannot|am unable to)|i'?m (?:not able|sorry,? but)|"
    r"as an ai language model|i don'?t have the ability)",
    re.IGNORECASE,
)
_ERROR_HINTS = re.compile(
    r"\b(?:traceback|exception|error:?)\b.*\b(?:line \d+|file \"[^\"]+\")",
    re.IGNORECASE,
)


# ── Doc-mode helpers ─────────────────────────────────────────────────────


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    if ext == ".pdf":
        import pdfplumber
        pages = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages.append(t)
        return "\n\n".join(pages)
    if ext == ".docx":
        from docx import Document
        doc = Document(str(path))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return path.read_text(encoding="utf-8", errors="replace")


def chunk_text(text: str, min_words: int = 200, max_words: int = 400) -> list[str]:
    words = text.split()
    out: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunk = " ".join(words[start:end])
        if len(chunk.split()) >= min_words or end >= len(words):
            out.append(chunk)
        start = end
    return out


def generate_question(first_sentence: str) -> str:
    try:
        import httpx
        resp = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": "qwen2.5-coder:3b",  # fastest; the question is throw-away
                "prompt": (
                    f"What question does this passage answer? Return ONLY the question.\n\n"
                    f'"{first_sentence}"'
                ),
                "stream": False,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip() or f"Explain: {first_sentence[:80]}"
    except Exception:
        return f"Explain: {first_sentence[:80]}"


# ── Chat-mode harvester ──────────────────────────────────────────────────


def _normalize_user_msg(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _looks_like_refusal_or_error(assistant_text: str) -> bool:
    sample = assistant_text[:1200]
    if _REFUSAL_HINTS.search(sample):
        return True
    if _ERROR_HINTS.search(sample):
        return True
    return False


def harvest_chats(chats_dir: Path) -> list[dict[str, str]]:
    """Walk data/chats/*.json, emit cleaned (prompt, completion) pairs."""
    out: list[dict[str, str]] = []
    seen_hashes: set[str] = set()
    files = sorted(chats_dir.glob("*.json"))
    if not files:
        return out
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        messages = data.get("messages") if isinstance(data, dict) else None
        if not isinstance(messages, list):
            continue
        # Pair every user message with the immediately following assistant message.
        i = 0
        while i < len(messages) - 1:
            cur = messages[i]
            nxt = messages[i + 1]
            i += 1
            if not (isinstance(cur, dict) and isinstance(nxt, dict)):
                continue
            if cur.get("role") != "user" or nxt.get("role") != "assistant":
                continue
            u = str(cur.get("content") or "").strip()
            a = str(nxt.get("content") or "").strip()
            if not (_MIN_USER_LEN <= len(u) <= _MAX_USER_LEN):
                continue
            if not (_MIN_ASSISTANT_LEN <= len(a) <= _MAX_ASSISTANT_LEN):
                continue
            if _looks_like_refusal_or_error(a):
                continue
            key = hashlib.sha1(_normalize_user_msg(u).encode("utf-8")).hexdigest()
            if key in seen_hashes:
                continue
            seen_hashes.add(key)
            out.append({"prompt": u, "completion": a})
    return out


# ── Main ─────────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(description="Build a JSONL training corpus.")
    p.add_argument("--from-chats", action="store_true",
                   help="Harvest pairs from data/chats/*.json (preferred — real user style).")
    p.add_argument("--chats-dir", default="data/chats",
                   help="Where chat JSON files live (default: data/chats).")
    p.add_argument("--from-docs", default=None,
                   help="Optional directory of .txt/.md/.pdf/.docx to mix in.")
    p.add_argument("--output", default="data/corpus/training.jsonl")
    p.add_argument("--min-pairs", type=int, default=20,
                   help="Refuse to write the corpus if fewer than this many pairs are produced.")
    args = p.parse_args()

    if not args.from_chats and not args.from_docs:
        p.error("Specify at least one source: --from-chats and/or --from-docs <dir>")

    rows: list[dict[str, str]] = []

    if args.from_chats:
        chats_dir = Path(args.chats_dir)
        if not chats_dir.is_dir():
            print(f"Chats dir not found: {chats_dir}", file=sys.stderr)
        else:
            harvested = harvest_chats(chats_dir)
            print(f"Harvested {len(harvested)} pairs from {chats_dir}")
            rows.extend(harvested)

    if args.from_docs:
        docs_dir = Path(args.from_docs)
        if not docs_dir.is_dir():
            print(f"Docs dir not found: {docs_dir}", file=sys.stderr)
            sys.exit(1)
        extensions = {".txt", ".md", ".pdf", ".docx"}
        files = [f for f in docs_dir.rglob("*") if f.suffix.lower() in extensions]
        print(f"Found {len(files)} doc files")
        for i, fp in enumerate(files):
            print(f"  [{i + 1}/{len(files)}] {fp.name}")
            try:
                text = extract_text(fp)
                for ch in chunk_text(text):
                    first = (ch.split(".")[0] + ".")[:240]
                    rows.append({"prompt": generate_question(first), "completion": ch})
            except Exception as exc:
                print(f"    error: {exc}")

    if len(rows) < args.min_pairs:
        print(f"Refusing to write corpus: only {len(rows)} pairs (min {args.min_pairs}). "
              f"Use --min-pairs to override.", file=sys.stderr)
        sys.exit(2)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    avg_completion = sum(len(r["completion"].split()) for r in rows) / max(len(rows), 1)
    print()
    print(f"Wrote {len(rows)} pairs to {out_path}")
    print(f"Average completion length: {avg_completion:.0f} words")
    print(f"Next: python scripts/finetune.py --corpus {out_path}")


if __name__ == "__main__":
    main()
