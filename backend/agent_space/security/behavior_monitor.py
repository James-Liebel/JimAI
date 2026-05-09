"""BehaviorMonitor — heuristic agent-loop watchdog.

OWASP Agentic Top-10 (2026) lists "Agentic Resource Exhaustion" as a real
class of attack: a malicious or buggy agent that loops forever, drains a
token budget, or repeats the same tool call until the host runs out of disk.
This watchdog catches the cheap-to-detect cases without needing a separate
ML model:

    * iteration cap     -- max steps per run
    * wall-clock cap    -- max seconds per run
    * step dedup        -- block identical tool/args within last N steps
    * tool-sequence n-gram -- flag repeated patterns like read,read,read
    * token budget      -- track approximate token usage per run

Each violation raises a BehaviorViolation with severity. Severity is the
caller's signal; depending on policy, the orchestrator can warn, throttle,
or terminate the run.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BehaviorViolation:
    rule: str
    severity: str  # "info" | "warn" | "halt"
    message: str
    at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_args(args: dict[str, Any] | None) -> str:
    if not args:
        return ""
    # Stable, compact key=value snippet for hashing.
    parts: list[str] = []
    for key in sorted(args):
        value = args[key]
        if isinstance(value, (str, int, float, bool)):
            text = str(value)[:200]
        else:
            try:
                import json
                text = json.dumps(value, ensure_ascii=False, default=str)[:200]
            except Exception:
                text = str(value)[:200]
        parts.append(f"{key}={text}")
    return "|".join(parts)


@dataclass
class _RunState:
    run_id: str
    started_at: float
    step_count: int = 0
    last_step_at: float = 0.0
    token_estimate: int = 0
    history: deque = field(default_factory=lambda: deque(maxlen=12))
    violations: list[BehaviorViolation] = field(default_factory=list)


class RunGuard:
    """Per-run guard returned by :meth:`BehaviorMonitor.start_run`.

    Used as a context manager around the run loop. Each step calls
    ``record_step`` before executing the tool; that may raise
    :class:`BehaviorViolation` (severity=halt) which the run loop is
    expected to honor.
    """

    def __init__(self, monitor: "BehaviorMonitor", state: _RunState) -> None:
        self.monitor = monitor
        self.state = state

    @property
    def step_count(self) -> int:
        return self.state.step_count

    @property
    def violations(self) -> list[BehaviorViolation]:
        return list(self.state.violations)

    def record_step(self, *, tool: str, args: dict[str, Any] | None = None, est_tokens: int = 0) -> BehaviorViolation | None:
        return self.monitor._record_step(self.state, tool=tool, args=args, est_tokens=est_tokens)

    def end(self, *, status: str = "ok") -> dict[str, Any]:
        return self.monitor._end_run(self.state, status=status)


class BehaviorMonitor:
    """Heuristic guard. No external dependencies."""

    def __init__(
        self,
        *,
        max_steps: int = 30,
        max_wall_seconds: float = 600.0,
        dedup_window: int = 4,
        ngram_repeat_threshold: int = 3,
        token_budget: int = 200_000,
    ) -> None:
        self.max_steps = int(max_steps)
        self.max_wall_seconds = float(max_wall_seconds)
        self.dedup_window = max(1, int(dedup_window))
        self.ngram_repeat_threshold = max(2, int(ngram_repeat_threshold))
        self.token_budget = int(token_budget)
        self._runs: dict[str, _RunState] = {}
        self._stats = {
            "runs_started": 0,
            "runs_ended": 0,
            "violations_total": 0,
            "halt_violations": 0,
        }

    def start_run(self, run_id: str | None = None) -> RunGuard:
        rid = run_id or uuid.uuid4().hex
        state = _RunState(run_id=rid, started_at=time.time())
        self._runs[rid] = state
        self._stats["runs_started"] += 1
        return RunGuard(self, state)

    def _record_step(
        self,
        state: _RunState,
        *,
        tool: str,
        args: dict[str, Any] | None,
        est_tokens: int = 0,
    ) -> BehaviorViolation | None:
        state.step_count += 1
        state.last_step_at = time.time()
        if est_tokens > 0:
            state.token_estimate += int(est_tokens)
        sig = f"{tool}|{_normalize_args(args)}"
        state.history.append((tool, sig))

        # Iteration cap.
        if state.step_count > self.max_steps:
            return self._record_violation(
                state, "iteration_cap", "halt",
                f"exceeded max_steps={self.max_steps}",
                metadata={"step_count": state.step_count},
            )

        # Wall-clock cap.
        elapsed = state.last_step_at - state.started_at
        if elapsed > self.max_wall_seconds:
            return self._record_violation(
                state, "wall_clock_cap", "halt",
                f"exceeded max_wall_seconds={self.max_wall_seconds:.0f} (elapsed={elapsed:.0f}s)",
                metadata={"elapsed": elapsed},
            )

        # Token budget.
        if self.token_budget > 0 and state.token_estimate > self.token_budget:
            return self._record_violation(
                state, "token_budget", "halt",
                f"exceeded token_budget={self.token_budget} (used={state.token_estimate})",
                metadata={"token_estimate": state.token_estimate},
            )

        # Step dedup against recent window.
        recent = list(state.history)[-1 - self.dedup_window:-1]
        if any(prev_sig == sig for _prev_tool, prev_sig in recent):
            return self._record_violation(
                state, "step_dedup", "warn",
                f"identical {tool} call within last {self.dedup_window} steps",
                metadata={"tool": tool},
            )

        # Tool-sequence n-gram repeat.
        if len(state.history) >= self.ngram_repeat_threshold:
            tail_tools = [t for t, _sig in list(state.history)[-self.ngram_repeat_threshold:]]
            if all(x == tail_tools[0] for x in tail_tools):
                return self._record_violation(
                    state, "ngram_repeat", "warn",
                    f"tool '{tail_tools[0]}' repeated {self.ngram_repeat_threshold}x in a row",
                    metadata={"tool": tail_tools[0], "count": self.ngram_repeat_threshold},
                )

        return None

    def _record_violation(
        self,
        state: _RunState,
        rule: str,
        severity: str,
        message: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> BehaviorViolation:
        violation = BehaviorViolation(
            rule=rule,
            severity=severity,
            message=message,
            at=time.time(),
            metadata=dict(metadata or {}),
        )
        state.violations.append(violation)
        self._stats["violations_total"] += 1
        if severity == "halt":
            self._stats["halt_violations"] += 1
        logger.info("BehaviorMonitor %s [%s] run=%s msg=%s", severity, rule, state.run_id, message)
        return violation

    def _end_run(self, state: _RunState, *, status: str = "ok") -> dict[str, Any]:
        self._stats["runs_ended"] += 1
        elapsed = time.time() - state.started_at
        report = {
            "run_id": state.run_id,
            "status": status,
            "step_count": state.step_count,
            "elapsed": round(elapsed, 3),
            "token_estimate": state.token_estimate,
            "violations": [v.to_dict() for v in state.violations],
        }
        self._runs.pop(state.run_id, None)
        return report

    def report(self, run_id: str) -> dict[str, Any] | None:
        state = self._runs.get(run_id)
        if state is None:
            return None
        return {
            "run_id": run_id,
            "step_count": state.step_count,
            "elapsed": round(time.time() - state.started_at, 3),
            "token_estimate": state.token_estimate,
            "violations": [v.to_dict() for v in state.violations],
            "active": True,
        }

    def stats(self) -> dict[str, Any]:
        return {**self._stats, "active_runs": len(self._runs)}
