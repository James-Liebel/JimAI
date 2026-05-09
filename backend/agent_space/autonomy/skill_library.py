"""Verifier-gated skill library — the compounding-capability layer.

Distinct from ``backend/agent_space/skill_store.py`` (which holds reusable
SKILL.md instruction documents). This library stores **proven artifacts**
captured from successful runs:

    * code blobs that passed tests
    * action sequences that achieved an objective
    * tool-call patterns the verifier confirmed

Retrieval works by similarity to a new objective. When a new run starts the
orchestrator can pull the top-k relevant entries and inject them as
few-shot examples — letting the platform improve without fine-tuning.

This is the Voyager / AutoSkill pattern recommended by 2026 agent-autonomy
research.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ..paths import DATA_ROOT
from .episodic_memory import _encode_vector, _cosine, EMBED_MODEL

logger = logging.getLogger(__name__)

LIBRARY_DIR = DATA_ROOT / "autonomy"
LIBRARY_FILE = LIBRARY_DIR / "skill_library.jsonl"


@dataclass
class SkillEntry:
    id: str
    created_at: float
    updated_at: float
    name: str
    description: str
    objective: str
    artifact_type: str  # "code" | "actions" | "prompt" | "trace"
    artifact: str
    tags: list[str] = field(default_factory=list)
    success_count: int = 1
    use_count: int = 0
    last_used_at: float = 0.0
    verifier_score: float = 1.0
    embedding_b64: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "SkillEntry":
        return cls(
            id=str(row.get("id") or uuid.uuid4().hex),
            created_at=float(row.get("created_at") or time.time()),
            updated_at=float(row.get("updated_at") or time.time()),
            name=str(row.get("name") or ""),
            description=str(row.get("description") or ""),
            objective=str(row.get("objective") or ""),
            artifact_type=str(row.get("artifact_type") or "code"),
            artifact=str(row.get("artifact") or ""),
            tags=list(row.get("tags") or []),
            success_count=int(row.get("success_count") or 1),
            use_count=int(row.get("use_count") or 0),
            last_used_at=float(row.get("last_used_at") or 0.0),
            verifier_score=float(row.get("verifier_score") or 1.0),
            embedding_b64=str(row.get("embedding_b64") or ""),
            metadata=dict(row.get("metadata") or {}),
        )

    def vector(self) -> np.ndarray | None:
        if not self.embedding_b64:
            return None
        import base64
        try:
            buf = base64.b64decode(self.embedding_b64.encode("ascii"))
            return np.frombuffer(buf, dtype=np.float32)
        except Exception:
            return None


class SkillLibrary:
    """Append-and-merge skill repository with similarity retrieval."""

    def __init__(self, *, file_path: Path = LIBRARY_FILE, embed_fn=None) -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._embed_fn = embed_fn  # injected for testability
        self._lock = asyncio.Lock()
        self._cache: dict[str, SkillEntry] | None = None

    def _ensure_loaded(self) -> None:
        if self._cache is not None:
            return
        cache: dict[str, SkillEntry] = {}
        if not self.file_path.exists():
            self._cache = cache
            return
        try:
            with self.file_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    entry = SkillEntry.from_dict(row)
                    cache[entry.id] = entry
        except OSError as exc:
            logger.warning("Failed to read skill library: %s", exc)
        self._cache = cache

    def _flush(self) -> None:
        if self._cache is None:
            return
        try:
            with self.file_path.open("w", encoding="utf-8") as fh:
                for entry in self._cache.values():
                    fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Failed to write skill library: %s", exc)

    async def capture(
        self,
        *,
        name: str,
        description: str,
        objective: str,
        artifact: str,
        artifact_type: str = "code",
        tags: list[str] | None = None,
        verifier_score: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> SkillEntry:
        """Store a verifier-approved artifact. Merges with existing entry by name."""
        async with self._lock:
            self._ensure_loaded()
            assert self._cache is not None
            now = time.time()
            existing = next(
                (e for e in self._cache.values() if e.name.strip().lower() == name.strip().lower()),
                None,
            )
            if existing is not None:
                existing.success_count += 1
                existing.updated_at = now
                existing.verifier_score = max(existing.verifier_score, float(verifier_score))
                if metadata:
                    existing.metadata.update(metadata)
                if artifact and len(artifact) > len(existing.artifact):
                    existing.artifact = artifact
                self._flush()
                return existing
            entry = SkillEntry(
                id=uuid.uuid4().hex,
                created_at=now,
                updated_at=now,
                name=name.strip() or f"skill-{uuid.uuid4().hex[:8]}",
                description=description.strip(),
                objective=objective.strip(),
                artifact_type=artifact_type,
                artifact=artifact,
                tags=[t.strip() for t in (tags or []) if t.strip()],
                verifier_score=float(verifier_score),
                metadata=dict(metadata or {}),
            )
            seed = f"{entry.name}\n{entry.description}\n{entry.objective}"
            if self._embed_fn is not None:
                try:
                    vec = await self._embed_fn(seed)
                    if vec is not None:
                        entry.embedding_b64 = _encode_vector(vec.tolist() if isinstance(vec, np.ndarray) else list(vec))
                except Exception as exc:
                    logger.debug("Embedding failed during skill capture: %s", exc)
            self._cache[entry.id] = entry
            self._flush()
            return entry

    async def retrieve(
        self,
        objective: str,
        *,
        limit: int = 5,
        min_score: float = 0.55,
        artifact_type: str | None = None,
    ) -> list[tuple[SkillEntry, float]]:
        async with self._lock:
            self._ensure_loaded()
            assert self._cache is not None
            if not self._cache:
                return []
            qvec: np.ndarray | None = None
            if self._embed_fn is not None:
                try:
                    raw = await self._embed_fn(objective)
                    if raw is not None:
                        qvec = np.asarray(raw, dtype=np.float32)
                except Exception as exc:
                    logger.debug("Embedding failed during retrieve: %s", exc)
            scored: list[tuple[SkillEntry, float]] = []
            obj_tokens = {tok for tok in objective.lower().split() if len(tok) > 2}
            for entry in self._cache.values():
                if artifact_type and entry.artifact_type != artifact_type:
                    continue
                vec = entry.vector()
                score = 0.0
                if qvec is not None and vec is not None:
                    score = _cosine(qvec, vec)
                # token-overlap fallback so retrieval still works without embeddings
                blob = f"{entry.name} {entry.description} {entry.objective} {' '.join(entry.tags)}".lower()
                blob_tokens = {tok for tok in blob.split() if len(tok) > 2}
                if obj_tokens and blob_tokens:
                    overlap = len(obj_tokens & blob_tokens) / max(len(obj_tokens), 1)
                    score = max(score, overlap * 0.6)
                # success boost
                score += min(0.1, 0.02 * entry.success_count)
                if score < min_score:
                    continue
                scored.append((entry, score))
            scored.sort(key=lambda row: row[1], reverse=True)
            top = scored[: max(1, int(limit))]
            now = time.time()
            for entry, _score in top:
                entry.use_count += 1
                entry.last_used_at = now
            if top:
                self._flush()
            return top

    def list_all(self, *, limit: int = 500) -> list[SkillEntry]:
        self._ensure_loaded()
        assert self._cache is not None
        rows = list(self._cache.values())
        rows.sort(key=lambda e: (e.success_count, e.updated_at), reverse=True)
        return rows[: max(1, int(limit))]

    def stats(self) -> dict[str, Any]:
        self._ensure_loaded()
        assert self._cache is not None
        if not self._cache:
            return {"count": 0, "total_uses": 0, "avg_success": 0.0}
        rows = list(self._cache.values())
        total_uses = sum(e.use_count for e in rows)
        avg_success = float(sum(e.success_count for e in rows)) / max(1, len(rows))
        by_type: dict[str, int] = {}
        for entry in rows:
            by_type[entry.artifact_type] = by_type.get(entry.artifact_type, 0) + 1
        return {
            "count": len(rows),
            "total_uses": total_uses,
            "avg_success": round(avg_success, 2),
            "by_type": by_type,
            "embedded": sum(1 for e in rows if e.embedding_b64),
        }

    async def delete(self, entry_id: str) -> bool:
        async with self._lock:
            self._ensure_loaded()
            assert self._cache is not None
            if entry_id not in self._cache:
                return False
            del self._cache[entry_id]
            self._flush()
            return True

    @staticmethod
    def render_for_prompt(entries: list[tuple["SkillEntry", float]], *, max_chars: int = 4000) -> str:
        """Format retrieved entries as a few-shot context block."""
        lines: list[str] = []
        used = 0
        for entry, score in entries:
            block = (
                f"--- prior winning approach (score={score:.2f}, success_count={entry.success_count}) ---\n"
                f"name: {entry.name}\n"
                f"objective: {entry.objective[:240]}\n"
                f"description: {entry.description[:240]}\n"
                f"artifact_type: {entry.artifact_type}\n"
                f"artifact:\n{entry.artifact[:1600]}\n"
            )
            if used + len(block) > max_chars:
                break
            lines.append(block)
            used += len(block)
        if not lines:
            return ""
        return "\n".join(lines)
