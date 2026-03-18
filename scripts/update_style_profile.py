"""Update style profile based on approved feedback (thumbs up responses)."""

import json
import re
import sys
from collections import Counter
from pathlib import Path


# Common English stopwords
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "it", "its",
    "this", "that", "these", "those", "i", "you", "he", "she", "we",
    "they", "me", "him", "her", "us", "them", "my", "your", "his",
    "our", "their", "not", "no", "so", "if", "as", "then", "than",
}


def analyze_text(texts: list[str]) -> dict:
    """Analyze a collection of texts and extract style metrics."""
    all_words: list[str] = []
    sentence_lengths: list[int] = []
    bigrams: Counter = Counter()

    for text in texts:
        words = re.findall(r"\b\w+\b", text.lower())
        all_words.extend(words)

        sentences = re.split(r"[.!?]+", text)
        for sent in sentences:
            sent_words = sent.split()
            if sent_words:
                sentence_lengths.append(len(sent_words))

        # Count bigrams
        for i in range(len(words) - 1):
            bigrams[(words[i], words[i + 1])] += 1

    # Top vocabulary (excluding stopwords)
    word_freq = Counter(w for w in all_words if w not in STOPWORDS and len(w) > 2)
    top_words = [w for w, _ in word_freq.most_common(50)]

    # Top bigrams (excluding stopwords)
    top_bigrams = [
        f"{a} {b}"
        for (a, b), _ in bigrams.most_common(20)
        if a not in STOPWORDS and b not in STOPWORDS
    ]

    avg_sent_len = sum(sentence_lengths) / len(sentence_lengths) if sentence_lengths else 0

    return {
        "avg_sentence_length": round(avg_sent_len, 1),
        "top_vocabulary": top_words[:20],
        "common_bigrams": top_bigrams[:10],
    }


def main():
    feedback_path = Path("data/feedback.jsonl")
    profile_path = Path("data/style_profile.json")

    if not feedback_path.exists():
        print("No feedback file found.")
        sys.exit(0)

    # Load approved responses (thumbs up)
    approved_texts: list[str] = []
    with open(feedback_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("thumbs_up"):
                # The prompt's response was approved
                approved_texts.append(entry.get("prompt", ""))
            if entry.get("correction"):
                # User provided a preferred version
                approved_texts.append(entry["correction"])

    if not approved_texts:
        print("No approved feedback found yet.")
        sys.exit(0)

    print(f"Analyzing {len(approved_texts)} approved texts...")

    metrics = analyze_text(approved_texts)

    # Load existing profile
    if profile_path.exists():
        old_profile = json.loads(profile_path.read_text(encoding="utf-8"))
    else:
        old_profile = {}

    # Merge new metrics
    new_profile = {**old_profile}
    new_profile["learned_metrics"] = metrics

    # Update sentence_length description based on data
    avg = metrics["avg_sentence_length"]
    if avg < 10:
        new_profile["sentence_length"] = "predominantly short, punchy sentences"
    elif avg < 20:
        new_profile["sentence_length"] = "mix of short punchy sentences and longer analytical ones"
    else:
        new_profile["sentence_length"] = "tends toward longer, more detailed sentences"

    # Save updated profile
    profile_path.write_text(json.dumps(new_profile, indent=2), encoding="utf-8")

    # Print diff
    print("\nStyle Profile Changes:")
    print("-" * 40)
    for key in set(list(old_profile.keys()) + list(new_profile.keys())):
        old_val = old_profile.get(key)
        new_val = new_profile.get(key)
        if old_val != new_val:
            print(f"  {key}:")
            print(f"    OLD: {old_val}")
            print(f"    NEW: {new_val}")
    print("-" * 40)
    print(f"\nProfile saved to {profile_path}")


if __name__ == "__main__":
    main()
