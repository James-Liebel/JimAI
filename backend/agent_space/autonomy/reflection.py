"""Reflexion-style verbal feedback loop.

After a verifier rejects an output, ask the LLM to produce a short verbal
critique focused on *why* it failed and *what to try differently*. Append
this critique to the next attempt's prompt. The original Reflexion paper
(arXiv:2303.11366) calls this "verbal RL" — no weights are updated, only
the prompt grows with the lesson.

Key constraints learned from production deployments:
    * Cap reflection text length so prompt growth is bounded.
    * Cap reflection iterations (3-5) so the loop terminates.
    * Persist reflections per-objective so future retries with similar
      objectives benefit from prior lessons.
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

from models import ollama_client

from ..paths import DATA_ROOT

logger = logging.getLogger(__name__)

REFLECTIONS_DIR = DATA_ROOT / "autonomy"
REFLECTIONS_FILE = REFLECTIONS_DIR / "reflections.jsonl"

DEFAULT_MODEL = "qwen2.5-coder:14b"
MAX_REFLECTION_CHARS = 1200
MAX_LESSONS_IN_PROMPT = 4


@dataclass
class ReflectionTrace:
    id: str
    created_at: float
    run_id: str
    agent_id: str
    objective: str
    attempt: int
    failure_reason: str
    lesson: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "ReflectionTrace":
        return cls(
            id=str(row.get("id") or uuid.uuid4().hex),
            created_at=float(row.get("created_at") or time.time()),
            run_id=str(row.get("run_id") or ""),
            agent_id=str(row.get("agent_id") or ""),
            objective=str(row.get("objective") or ""),
            attempt=int(row.get("attempt") or 1),
            failure_reason=str(row.get("failure_reason") or ""),
            lesson=str(row.get("lesson") or ""),
            metadata=dict(row.get("metadata") or {}),
        )


class ReflectionEngine:
    """Generate, store, and retrieve verbal critiques across attempts."""

    def __init__(
        self,
        *,
        file_path: Path = REFLECTIONS_FILE,
        model: str = DEFAULT_MODEL,
        max_attempts: int = 4,
    ) -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.model = model
        self.max_attempts = int(max_attempts)
        self._lock = asyncio.Lock()
        self._cache: list[ReflectionTrace] | None = None

    def _ensure_loaded(self) -> None:
        if self._cache is not None:
            return
        rows: list[ReflectionTrace] = []
        if self.file_path.exists():
            try:
                with self.file_path.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rows.append(ReflectionTrace.from_dict(json.loads(line)))
                        except (json.JSONDecodeError, TypeError):
                            continue
            except OSError as exc:
                logger.warning("Failed to read reflections: %s", exc)
        self._cache = rows

    async def reflect(
        self,
        *,
        run_id: str,
        agent_id: str,
        objective: str,
        attempt: int,
        failure_reason: str,
        last_attempt_output: str = "",
        model: str | None = None,
    ) -> ReflectionTrace:
        """Ask the model for a short critique and persist it."""
        prompt = (
            "You are a self-reflective agent reviewing your own failed attempt.\n"
            "Write a SHORT lesson (max 5 sentences) capturing:\n"
            "1) the most likely root cause of the failure,\n"
            "2) the SPECIFIC change to make next time,\n"
            "3) any subtle assumption to challenge.\n"
            "Respond as plain prose. No headings, no JSON.\n\n"
            f"Objective: {objective.strip()[:600]}\n"
            f"Attempt #: {attempt}\n"
            f"Failure reason: {failure_reason.strip()[:1200]}\n"
        )
        if last_attempt_output.strip():
            tail = last_attempt_output.strip()
            if len(tail) > 1200:
                tail = tail[:1200] + "...(truncated)"
            prompt += f"\nLast attempt output (tail):\n{tail}\n"

        chosen = (model or self.model).strip()
        try:
            critique = await asyncio.wait_for(
                ollama_client.generate_full(
                    model=chosen,
                    prompt=prompt,
                    temperature=0.3,
                    num_predict=256,
                ),
                timeout=30,
            )
        except asyncio.TimeoutError:
            critique = (
                f"Attempt {attempt} failed because: {failure_reason[:200]}. "
                "Next attempt: re-read the objective, check assumptions, simplify scope."
            )
        except Exception as exc:
            logger.debug("Reflection generation failed: %s", exc)
            critique = (
                f"Attempt {attempt} hit '{failure_reason[:120]}'. "
                "Next attempt: validate inputs and re-check tool args."
            )

        critique = critique.strip()
        if len(critique) > MAX_REFLECTION_CHARS:
            critique = critique[:MAX_REFLECTION_CHARS] + "...(truncated)"

        trace = ReflectionTrace(
            id=uuid.uuid4().hex,
            created_at=time.time(),
            run_id=run_id,
            agent_id=agent_id,
            objective=objective.strip(),
            attempt=attempt,
            failure_reason=failure_reason.strip()[:2000],
            lesson=critique,
        )
        async with self._lock:
            self._ensure_loaded()
            assert self._cache is not None
            self._cache.append(trace)
            try:
                with self.file_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(trace.to_dict(), ensure_ascii=False) + "\n")
            except OSError as exc:
                logger.warning("Failed to append reflection: %s", exc)
        return trace

    def lessons_for(self, objective: str, *, limit: int = MAX_LESSONS_IN_PROMPT) -> list[ReflectionTrace]:
        """Token-overlap match — cheap and works without embeddings."""
        self._ensure_loaded()
        assert self._cache is not None
        if not self._cache:
            return []
        obj_tokens = {tok for tok in objective.lower().split() if len(tok) > 3}
        if not obj_tokens:
            return self._cache[-limit:]
        scored: list[tuple[float, ReflectionTrace]] = []
        for trace in self._cache:
            blob_tokens = {tok for tok in trace.objective.lower().split() if len(tok) > 3}
            if not blob_tokens:
                continue
            overlap = len(obj_tokens & blob_tokens) / max(len(obj_tokens), 1)
            if overlap < 0.2:
                continue
            scored.append((overlap, trace))
        scored.sort(key=lambda row: (row[0], row[1].created_at), reverse=True)
        return [trace for _score, trace in scored[: max(1, int(limit))]]

    @staticmethod
    def render_for_prompt(traces: list[ReflectionTrace]) -> str:
        if not traces:
            return ""
        lines = ["## Lessons from prior attempts (read before acting)"]
        for trace in traces:
            lines.append(f"- attempt {trace.attempt} on '{trace.objective[:80]}': {trace.lesson[:300]}")
        return "\n".join(lines)

    def stats(self) -> dict[str, Any]:
        self._ensure_loaded()
        assert self._cache is not None
        if not self._cache:
            return {"count": 0, "max_attempts_seen": 0, "runs": 0}
        runs = len({t.run_id for t in self._cache if t.run_id})
        return {
            "count": len(self._cache),
            "max_attempts_seen": max(t.attempt for t in self._cache),
            "runs": runs,
            "first_at": min(t.created_at for t in self._cache),
            "last_at": max(t.created_at for t in self._cache),
        }
