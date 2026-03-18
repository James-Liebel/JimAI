"""Build training corpus from a directory of documents."""

import argparse
import json
import sys
from pathlib import Path

import httpx

OLLAMA_URL = "http://localhost:11434"


def extract_text(path: Path) -> str:
    """Extract text from a file based on its extension."""
    ext = path.suffix.lower()
    if ext in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    elif ext == ".pdf":
        import pdfplumber
        pages = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
        return "\n\n".join(pages)
    elif ext == ".docx":
        from docx import Document
        doc = Document(str(path))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    else:
        return path.read_text(encoding="utf-8", errors="replace")


def chunk_text(text: str, min_words: int = 200, max_words: int = 400) -> list[str]:
    """Split text into chunks of approximately min_words to max_words."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunk = " ".join(words[start:end])
        if len(chunk.split()) >= min_words or end >= len(words):
            chunks.append(chunk)
        start = end
    return chunks


def generate_question(first_sentence: str) -> str:
    """Ask qwen3:8b to generate a question that the passage answers."""
    try:
        resp = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": "qwen3:8b",
                "prompt": (
                    f"What question does this passage answer? "
                    f"Return ONLY the question, nothing else.\n\n"
                    f'"{first_sentence}"'
                ),
                "stream": False,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception:
        return f"Explain: {first_sentence[:80]}"


def main():
    parser = argparse.ArgumentParser(description="Build training corpus from documents")
    parser.add_argument("directory", help="Directory containing documents")
    parser.add_argument("--output", default="data/corpus/training.jsonl", help="Output JSONL path")
    args = parser.parse_args()

    source_dir = Path(args.directory)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_dir.is_dir():
        print(f"Error: {source_dir} is not a directory")
        sys.exit(1)

    extensions = {".txt", ".md", ".pdf", ".docx"}
    files = [f for f in source_dir.rglob("*") if f.suffix.lower() in extensions]
    print(f"Found {len(files)} files to process")

    total_pairs = 0
    total_words = 0

    with open(output_path, "w", encoding="utf-8") as out:
        for i, file_path in enumerate(files):
            print(f"[{i+1}/{len(files)}] Processing: {file_path.name}")
            try:
                text = extract_text(file_path)
                chunks = chunk_text(text)
                for chunk in chunks:
                    first_sentence = chunk.split(".")[0] + "."
                    question = generate_question(first_sentence)
                    pair = {"prompt": question, "completion": chunk}
                    out.write(json.dumps(pair) + "\n")
                    total_pairs += 1
                    total_words += len(chunk.split())
            except Exception as exc:
                print(f"  Error: {exc}")

    avg_length = total_words / total_pairs if total_pairs else 0
    print(f"\nResults:")
    print(f"  Files processed: {len(files)}")
    print(f"  Training pairs: {total_pairs}")
    print(f"  Average completion length: {avg_length:.0f} words")
    print(f"  Output: {output_path}")
    print(f"  Estimated training time: ~{total_pairs * 2}s on RTX 5080")


if __name__ == "__main__":
    main()
