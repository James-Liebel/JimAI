"""Persistent episodic memory for autonomous runs.

Stores ``(timestamp, run_id, agent_id, event, outcome, summary, embedding)``
records on disk. Survives restarts. Indexed by simple cosine similarity over
nomic-embed-text vectors for retrieval before a new run starts.

Why episodic + not just vector:
    Vector recall is excellent for "have I seen something like this before"
    but loses chronology. Episodic rows preserve order so the agent can
    reconstruct what it tried, in what order, and which paths panned out.

Storage:
    JSONL at ``data/agent_space/autonomy/episodes.jsonl``. One row per event.
    Embeddings are stored inline as base64-encoded float32 to keep the file
    self-contained (no Chroma dependency for this layer).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from models import ollama_client

from ..paths import DATA_ROOT

logger = logging.getLogger(__name__)

EPISODES_DIR = DATA_ROOT / "autonomy"
EPISODES_FILE = EPISODES_DIR / "episodes.jsonl"

EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768
MAX_EPISODES = 50_000


@dataclass
class EpisodeRecord:
    id: str
    timestamp: float
    run_id: str
    agent_id: str
    event: str
    outcome: str
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding_b64: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "EpisodeRecord":
        return cls(
            id=str(row.get("id") or uuid.uuid4().hex),
            timestamp=float(row.get("timestamp") or time.time()),
            run_id=str(row.get("run_id") or ""),
            agent_id=str(row.get("agent_id") or ""),
            event=str(row.get("event") or ""),
            outcome=str(row.get("outcome") or ""),
            summary=str(row.get("summary") or ""),
            metadata=dict(row.get("metadata") or {}),
            embedding_b64=str(row.get("embedding_b64") or ""),
        )

    def vector(self) -> np.ndarray | None:
        if not self.embedding_b64:
            return None
        try:
            buf = base64.b64decode(self.embedding_b64.encode("ascii"))
            return np.frombuffer(buf, dtype=np.float32)
        except Exception:
            return None


def _encode_vector(vec: list[float]) -> str:
    arr = np.asarray(vec, dtype=np.float32)
    return base64.b64encode(arr.tobytes()).decode("ascii")


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class EpisodicMemory:
    """Append-only episodic store with nomic-embed-text similarity search."""

    def __init__(self, *, file_path: Path = EPISODES_FILE, max_records: int = MAX_EPISODES) -> None:
        self.file_path = Path(file_path)
        self.max_records = int(max_records)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        # In-memory cache: {id: (record, vector)}. Loaded lazily on first access.
        self._cache: dict[str, tuple[EpisodeRecord, np.ndarray | None]] | None = None

    # ------------------------------------------------------------------ load

    def _ensure_loaded(self) -> None:
        if self._cache is not None:
            return
        cache: dict[str, tuple[EpisodeRecord, np.ndarray | None]] = {}
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
                    record = EpisodeRecord.from_dict(row)
                    cache[record.id] = (record, record.vector())
        except OSError as exc:
            logger.warning("Failed to read episodes file: %s", exc)
        self._cache = cache

    # ----------------------------------------------------------------- write

    async def record(
        self,
        *,
        run_id: str,
        agent_id: str,
        event: str,
        outcome: str,
        summary: str,
        metadata: dict[str, Any] | None = None,
        embed: bool = True,
    ) -> EpisodeRecord:
        record = EpisodeRecord(
            id=uuid.uuid4().hex,
            timestamp=time.time(),
            run_id=str(run_id or ""),
            agent_id=str(agent_id or ""),
            event=str(event or ""),
            outcome=str(outcome or ""),
            summary=str(summary or ""),
            metadata=dict(metadata or {}),
        )
        if embed and summary.strip():
            try:
                vec = await self._embed(summary)
                if vec is not None:
                    record.embedding_b64 = _encode_vector(vec.tolist())
            except Exception as exc:
                logger.debug("Embedding failed for episode %s: %s", record.id, exc)

        async with self._lock:
            self._ensure_loaded()
            assert self._cache is not None
            self._cache[record.id] = (record, record.vector())
            self._enforce_cap()
            try:
                with self.file_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
            except OSError as exc:
                logger.warning("Failed to append episode: %s", exc)
        return record

    def _enforce_cap(self) -> None:
        if self._cache is None:
            return
        if len(self._cache) <= self.max_records:
            return
        # Drop oldest by timestamp.
        rows = sorted(self._cache.values(), key=lambda kv: kv[0].timestamp)
        keep = rows[-self.max_records:]
        self._cache = {rec.id: (rec, vec) for rec, vec in keep}
        # Rewrite file from cache.
        try:
            with self.file_path.open("w", encoding="utf-8") as fh:
                for rec, _vec in keep:
                    fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Failed to compact episodes: %s", exc)

    # ------------------------------------------------------------------ read

    def list_by_run(self, run_id: str, *, limit: int = 200) -> list[EpisodeRecord]:
        self._ensure_loaded()
        assert self._cache is not None
        rows = [rec for rec, _vec in self._cache.values() if rec.run_id == run_id]
        rows.sort(key=lambda r: r.timestamp)
        return rows[-max(1, limit):]

    def list_recent(self, *, limit: int = 200) -> list[EpisodeRecord]:
        self._ensure_loaded()
        assert self._cache is not None
        rows = [rec for rec, _vec in self._cache.values()]
        rows.sort(key=lambda r: r.timestamp, reverse=True)
        return rows[:max(1, limit)]

    async def search(self, query: str, *, limit: int = 5, min_score: float = 0.55) -> list[tuple[EpisodeRecord, float]]:
        self._ensure_loaded()
        assert self._cache is not None
        if not str(query or "").strip() or not self._cache:
            return []
        try:
            qvec = await self._embed(query)
        except Exception as exc:
            logger.debug("Embedding failed for search: %s", exc)
            qvec = None
        if qvec is None:
            return []
        scored: list[tuple[EpisodeRecord, float]] = []
        for rec, vec in self._cache.values():
            if vec is None:
                continue
            score = _cosine(qvec, vec)
            if score < min_score:
                continue
            scored.append((rec, score))
        scored.sort(key=lambda row: row[1], reverse=True)
        return scored[:max(1, limit)]

    def stats(self) -> dict[str, Any]:
        self._ensure_loaded()
        assert self._cache is not None
        if not self._cache:
            return {"count": 0, "embedded": 0, "first_at": 0.0, "last_at": 0.0, "runs": 0}
        rows = [rec for rec, _vec in self._cache.values()]
        embedded = sum(1 for _rec, vec in self._cache.values() if vec is not None)
        runs = len({r.run_id for r in rows if r.run_id})
        return {
            "count": len(rows),
            "embedded": embedded,
            "first_at": min(r.timestamp for r in rows),
            "last_at": max(r.timestamp for r in rows),
            "runs": runs,
        }

    async def consolidate(self, *, max_per_run: int = 3) -> int:
        """Squash oldest verbose episodes into compact summaries.

        Strategy: for any run with >max_per_run episodes, keep the last N and
        replace earlier ones with a single 'consolidated' record. The
        consolidated summary is the concatenation of original summaries,
        truncated. This is the cheap version of memory consolidation; future
        versions can ask the LLM to re-summarise.
        """
        self._ensure_loaded()
        assert self._cache is not None
        consolidated = 0
        by_run: dict[str, list[EpisodeRecord]] = {}
        for rec, _vec in self._cache.values():
            by_run.setdefault(rec.run_id, []).append(rec)
        new_cache: dict[str, tuple[EpisodeRecord, np.ndarray | None]] = {}
        for run_id, rows in by_run.items():
            rows.sort(key=lambda r: r.timestamp)
            if len(rows) <= max_per_run:
                for rec in rows:
                    new_cache[rec.id] = (rec, rec.vector())
                continue
            keep = rows[-max_per_run:]
            squash = rows[:-max_per_run]
            digest = " | ".join(s.summary[:160] for s in squash)
            digest_summary = f"[consolidated {len(squash)} earlier events] {digest[:1200]}"
            try:
                vec = await self._embed(digest_summary)
            except Exception:
                vec = None
            digest_record = EpisodeRecord(
                id=uuid.uuid4().hex,
                timestamp=squash[0].timestamp,
                run_id=run_id,
                agent_id="memory",
                event="consolidated",
                outcome="ok",
                summary=digest_summary,
                metadata={"squashed_count": len(squash)},
                embedding_b64=_encode_vector(vec.tolist()) if vec is not None else "",
            )
            new_cache[digest_record.id] = (digest_record, vec)
            for rec in keep:
                new_cache[rec.id] = (rec, rec.vector())
            consolidated += len(squash)

        async with self._lock:
            self._cache = new_cache
            try:
                with self.file_path.open("w", encoding="utf-8") as fh:
                    for rec, _vec in new_cache.values():
                        fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
            except OSError as exc:
                logger.warning("Failed to write consolidated episodes: %s", exc)
        return consolidated

    # --------------------------------------------------------------- helpers

    async def _embed(self, text: str) -> np.ndarray | None:
        snippet = (text or "").strip()
        if not snippet:
            return None
        if len(snippet) > 6000:
            snippet = snippet[:6000]
        try:
            vec = await ollama_client.embed(snippet)
        except Exception as exc:
            logger.debug("Embed call failed: %s", exc)
            return None
        if not isinstance(vec, list) or not vec:
            return None
        try:
            return np.asarray(vec, dtype=np.float32)
        except Exception:
            return None
