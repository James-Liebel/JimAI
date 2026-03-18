"""Prompt construction utilities — RAG augmentation and style injection."""

import json
from pathlib import Path


def load_style_profile() -> dict:
    """Load the writing style profile from disk."""
    path = Path(__file__).resolve().parent.parent.parent / "data" / "style_profile.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def build_style_system_prompt(profile: dict) -> str:
    """Convert a style profile dict into a system prompt string."""
    if not profile:
        return "Write clearly and directly."
    return (
        f"Write in this exact style: {profile.get('sentence_length', '')}. "
        f"Vocabulary: {profile.get('vocabulary', '')}. "
        f"Structure: {profile.get('structure', '')}. "
        f"Tone: {profile.get('tone', '')}. "
        f"Never use these phrases: {', '.join(profile.get('avoid', []))}. "
        f"Math style: {profile.get('math_style', '')}. "
        f"Code style: {profile.get('code_style', '')}."
    )


def build_rag_prompt(user_message: str, chunks: list[dict]) -> str:
    """Augment a user message with retrieved context chunks.

    Each chunk should have 'source' and 'text' keys.
    """
    if not chunks:
        return user_message
    context_lines = [f"[{c['source']}]: {c['text']}" for c in chunks]
    context = "\n".join(context_lines)
    return (
        f"Relevant context from your knowledge base:\n{context}\n\n"
        f"Question: {user_message}"
    )
