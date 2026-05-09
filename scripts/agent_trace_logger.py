"""Trace logger for agent runs.

Captures the structured trace of an agent's run for later use in:
    1) self-improvement (filter by verifier success, retrain on winners)
    2) eval (replay traces against new model versions)
    3) debugging (human-readable timeline)

Trace shape (one JSONL row per step):
    {
      "trace_id": "...", "step": 0, "ts": ..., "run_id": "...",
      "agent_id": "planner", "kind": "thought" | "action" | "observation" | "verdict",
      "content": "...",          # free text for thought/observation/verdict
      "tool": "read_file",       # action only
      "args": {...},             # action only
      "success": true|false,     # observation/verdict only
      "metadata": {...}
    }

The orchestrator can append to the trace via TraceLogger.record_step().
A separate helper :func:`load_traces` reads them back grouped by trace_id
for downstream tooling.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# Repo-relative default; CLI lets caller override.
DEFAULT_TRACE_DIR = Path("data/agent_space/autonomy/traces")


@dataclass
class TraceStep:
    trace_id: str
    step: int
    ts: float
    run_id: str
    agent_id: str
    kind: str
    content: str = ""
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    success: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TraceLogger:
    """Append-only JSONL writer per day, grouped by trace_id."""

    def __init__(self, trace_dir: Path = DEFAULT_TRACE_DIR) -> None:
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self._step_counters: dict[str, int] = {}

    def _file_for_today(self) -> Path:
        return self.trace_dir / f"{time.strftime('%Y-%m-%d', time.gmtime())}.jsonl"

    def new_trace(self, run_id: str = "") -> str:
        trace_id = uuid.uuid4().hex
        self._step_counters[trace_id] = 0
        return trace_id

    def record_step(
        self,
        *,
        trace_id: str,
        run_id: str,
        agent_id: str,
        kind: str,
        content: str = "",
        tool: str = "",
        args: dict[str, Any] | None = None,
        success: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceStep:
        step_num = self._step_counters.get(trace_id, 0)
        self._step_counters[trace_id] = step_num + 1
        step = TraceStep(
            trace_id=trace_id,
            step=step_num,
            ts=time.time(),
            run_id=run_id,
            agent_id=agent_id,
            kind=kind,
            content=str(content or "")[:4000],
            tool=str(tool or ""),
            args=dict(args or {}),
            success=success,
            metadata=dict(metadata or {}),
        )
        try:
            with self._file_for_today().open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(step.to_dict(), ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            logger.warning("trace write failed: %s", exc)
        return step

    def close_trace(
        self,
        *,
        trace_id: str,
        run_id: str,
        success: bool,
        summary: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> TraceStep:
        return self.record_step(
            trace_id=trace_id,
            run_id=run_id,
            agent_id="trace",
            kind="verdict",
            content=summary,
            success=success,
            metadata=metadata or {},
        )


def load_traces(
    trace_dir: Path = DEFAULT_TRACE_DIR,
    *,
    only_successful: bool = False,
    after_ts: float = 0.0,
    limit: int | None = None,
) -> list[list[TraceStep]]:
    """Group rows by trace_id and return as a list of step-lists."""
    grouped: dict[str, list[TraceStep]] = {}
    if not trace_dir.exists():
        return []
    files = sorted(trace_dir.glob("*.jsonl"))
    for fp in files:
        try:
            with fp.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if float(row.get("ts") or 0) < after_ts:
                        continue
                    step = TraceStep(
                        trace_id=str(row.get("trace_id") or ""),
                        step=int(row.get("step") or 0),
                        ts=float(row.get("ts") or 0),
                        run_id=str(row.get("run_id") or ""),
                        agent_id=str(row.get("agent_id") or ""),
                        kind=str(row.get("kind") or "thought"),
                        content=str(row.get("content") or ""),
                        tool=str(row.get("tool") or ""),
                        args=dict(row.get("args") or {}),
                        success=row.get("success"),
                        metadata=dict(row.get("metadata") or {}),
                    )
                    grouped.setdefault(step.trace_id, []).append(step)
        except OSError as exc:
            logger.warning("could not read trace file %s: %s", fp, exc)
    out: list[list[TraceStep]] = []
    for trace_id, steps in grouped.items():
        steps.sort(key=lambda s: s.step)
        if only_successful:
            verdicts = [s for s in steps if s.kind == "verdict"]
            if not verdicts or not verdicts[-1].success:
                continue
        out.append(steps)
    out.sort(key=lambda steps: steps[0].ts if steps else 0.0, reverse=True)
    if limit is not None:
        out = out[: max(1, int(limit))]
    return out


def trace_to_react_text(steps: Iterable[TraceStep]) -> str:
    """Format a trace as a ReAct-style transcript for SFT."""
    lines: list[str] = []
    for step in steps:
        if step.kind == "thought":
            lines.append(f"Thought: {step.content}")
        elif step.kind == "action":
            args_text = json.dumps(step.args or {}, ensure_ascii=False)
            lines.append(f"Action: {step.tool}({args_text})")
        elif step.kind == "observation":
            lines.append(f"Observation: {step.content[:500]}")
        elif step.kind == "verdict":
            ok = "SUCCESS" if step.success else "FAILURE"
            lines.append(f"Verdict: {ok} — {step.content}")
    return "\n".join(lines)


def cli() -> int:
    parser = argparse.ArgumentParser(description="Inspect agent trace logs")
    parser.add_argument("--trace-dir", default=str(DEFAULT_TRACE_DIR))
    parser.add_argument("--list", action="store_true", help="list traces")
    parser.add_argument("--successful", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--show", help="show a single trace by id")
    args = parser.parse_args()

    trace_dir = Path(args.trace_dir)
    traces = load_traces(trace_dir, only_successful=args.successful, limit=args.limit)
    if args.show:
        for steps in traces:
            if steps and steps[0].trace_id == args.show:
                print(trace_to_react_text(steps))
                return 0
        print("trace not found", file=sys.stderr)
        return 1
    if args.list or not args.show:
        for steps in traces:
            if not steps:
                continue
            head = steps[0]
            verdict = next((s for s in reversed(steps) if s.kind == "verdict"), None)
            ok = "ok" if (verdict and verdict.success) else ("fail" if verdict else "incomplete")
            print(f"{head.trace_id}  steps={len(steps)}  run={head.run_id[:8]}  status={ok}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(cli())
