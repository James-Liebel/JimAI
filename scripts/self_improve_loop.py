"""End-to-end self-improvement loop for local agents.

Pipeline:

    1. read recent successful traces from data/.../traces/*.jsonl
    2. convert to ReAct-format SFT pairs (prompt + completion)
    3. append to data/corpus/agent_traces.jsonl
    4. invoke scripts/finetune.py to retrain a LoRA adapter
    5. run scripts/agent_eval.py against the candidate
    6. compare to frozen baseline; promote if win-rate improves >5%

Designed to be run as a cron / heartbeat job. Each step is bounded so a
single failure can't lock the pipeline.

Idempotent: each run records its checkpoint in
``data/agent_space/autonomy/self_improve_state.json``. Successive runs
only process traces newer than the last successful checkpoint.

Usage::

    python scripts/self_improve_loop.py --base-model qwen2.5-coder:14b
    python scripts/self_improve_loop.py --base-model qwen2.5-coder:14b --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))

from agent_trace_logger import (  # noqa: E402
    DEFAULT_TRACE_DIR,
    TraceStep,
    load_traces,
    trace_to_react_text,
)

logger = logging.getLogger(__name__)

DEFAULT_STATE_FILE = ROOT / "data/agent_space/autonomy/self_improve_state.json"
DEFAULT_CORPUS_PATH = ROOT / "data/corpus/agent_traces.jsonl"
DEFAULT_BASELINE_REPORT = ROOT / "data/agent_space/autonomy/eval_baseline.json"
DEFAULT_CANDIDATE_REPORT = ROOT / "data/agent_space/autonomy/eval_candidate.json"

MIN_TRACES_TO_RETRAIN = 25
PROMOTE_DELTA = 0.05


@dataclass
class LoopReport:
    started_at: float
    base_model: str
    candidate_tag: str
    new_traces: int
    sft_pairs_appended: int
    finetune_invoked: bool
    candidate_eval_success_rate: float
    baseline_eval_success_rate: float
    delta: float
    verdict: str  # "promote" | "neutral" | "regress" | "skip" | "error"
    notes: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"last_checkpoint_ts": 0.0, "last_run_at": 0.0, "history": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"last_checkpoint_ts": 0.0, "last_run_at": 0.0, "history": []}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def _trace_to_sft_pair(steps: list[TraceStep]) -> dict[str, str] | None:
    if not steps:
        return None
    objective_step = next(
        (s for s in steps if s.kind == "thought" and "objective" in s.content.lower()),
        None,
    )
    objective = objective_step.content if objective_step else (steps[0].content or "")
    transcript = trace_to_react_text(steps)
    if not objective.strip() or not transcript.strip():
        return None
    sft_system = (
        "You are an autonomous coding agent operating inside the JimAI workspace.\n"
        "Operating standards:\n"
        "- Follow the ReAct format strictly (Thought / Action / Observation).\n"
        "- Reference files as path/to/file.py:line so the user can jump to source.\n"
        "- Prefer extending existing patterns over inventing new abstractions.\n"
        "- Match the codebase: typed Python, no bare except, pathlib for paths.\n"
        "- Be terse. State the next action; do not narrate your deliberation.\n"
        "- Treat secrets and .env content as untouchable."
    )
    return {
        "prompt": (
            f"{sft_system}\n\n"
            f"Objective: {objective.strip()[:600]}"
        ),
        "completion": transcript[:6000],
    }


def _append_sft_pairs(corpus_path: Path, pairs: list[dict[str, str]]) -> int:
    if not pairs:
        return 0
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    with corpus_path.open("a", encoding="utf-8") as fh:
        for pair in pairs:
            fh.write(json.dumps(pair, ensure_ascii=False) + "\n")
    return len(pairs)


def _run_subprocess(args: list[str], *, cwd: Path, timeout: int) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            args, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        return -1, "", f"timeout: {exc}"
    return result.returncode, result.stdout, result.stderr


def _have_unsloth() -> bool:
    try:
        __import__("unsloth")
        return True
    except ImportError:
        return False


def _read_eval_report(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def run_loop(
    *,
    base_model: str,
    state_path: Path = DEFAULT_STATE_FILE,
    trace_dir: Path = DEFAULT_TRACE_DIR,
    corpus_path: Path = DEFAULT_CORPUS_PATH,
    baseline_path: Path = DEFAULT_BASELINE_REPORT,
    candidate_path: Path = DEFAULT_CANDIDATE_REPORT,
    candidate_tag: str | None = None,
    min_traces: int = MIN_TRACES_TO_RETRAIN,
    promote_delta: float = PROMOTE_DELTA,
    dry_run: bool = False,
) -> LoopReport:
    start = time.time()
    notes: list[str] = []
    candidate_tag = candidate_tag or f"agent:{time.strftime('%Y-%m-%d', time.gmtime(start))}"
    state = _load_state(state_path)
    last_ts = float(state.get("last_checkpoint_ts") or 0.0)

    traces = load_traces(trace_dir, only_successful=True, after_ts=last_ts, limit=2000)
    new_count = len(traces)
    sft_pairs = [_trace_to_sft_pair(t) for t in traces]
    sft_pairs = [p for p in sft_pairs if p is not None]

    if new_count < min_traces:
        notes.append(
            f"only {new_count} new successful traces (< {min_traces} threshold); skipping fine-tune"
        )
        return LoopReport(
            started_at=start,
            base_model=base_model,
            candidate_tag=candidate_tag,
            new_traces=new_count,
            sft_pairs_appended=0,
            finetune_invoked=False,
            candidate_eval_success_rate=0.0,
            baseline_eval_success_rate=float(_read_eval_report(baseline_path).get("success_rate") or 0.0),
            delta=0.0,
            verdict="skip",
            notes=notes,
            duration_seconds=round(time.time() - start, 3),
        )

    appended = 0 if dry_run else _append_sft_pairs(corpus_path, sft_pairs)
    notes.append(f"appended {appended} SFT pairs to {corpus_path}")

    finetune_invoked = False
    if dry_run:
        notes.append("dry-run: skipping finetune subprocess")
    elif not _have_unsloth():
        notes.append("unsloth not installed; skipping finetune (run pip install unsloth)")
    else:
        rc, out, err = _run_subprocess(
            [sys.executable, str(ROOT / "scripts/finetune.py")],
            cwd=ROOT,
            timeout=60 * 90,
        )
        finetune_invoked = True
        if rc == 0:
            notes.append("finetune completed successfully")
        else:
            notes.append(f"finetune failed rc={rc}: {(err or out)[:600]}")

    rc, _out, err = _run_subprocess(
        [
            sys.executable,
            str(ROOT / "scripts/agent_eval.py"),
            "--model",
            base_model,
            "--output",
            str(candidate_path),
        ],
        cwd=ROOT,
        timeout=60 * 30,
    )
    if rc != 0:
        notes.append(f"candidate eval failed rc={rc}: {err[:300]}")
        return LoopReport(
            started_at=start,
            base_model=base_model,
            candidate_tag=candidate_tag,
            new_traces=new_count,
            sft_pairs_appended=appended,
            finetune_invoked=finetune_invoked,
            candidate_eval_success_rate=0.0,
            baseline_eval_success_rate=float(_read_eval_report(baseline_path).get("success_rate") or 0.0),
            delta=0.0,
            verdict="error",
            notes=notes,
            duration_seconds=round(time.time() - start, 3),
        )

    candidate_report = _read_eval_report(candidate_path)
    baseline_report = _read_eval_report(baseline_path)
    candidate_rate = float(candidate_report.get("success_rate") or 0.0)
    baseline_rate = float(baseline_report.get("success_rate") or 0.0)
    delta = candidate_rate - baseline_rate
    verdict: str
    if not baseline_report:
        verdict = "promote"
        notes.append("no prior baseline; candidate becomes the baseline")
        if not dry_run:
            shutil.copyfile(candidate_path, baseline_path)
    elif delta >= promote_delta:
        verdict = "promote"
        notes.append(f"candidate beats baseline by +{delta:.3f}; promoting baseline")
        if not dry_run:
            shutil.copyfile(candidate_path, baseline_path)
    elif delta <= -promote_delta:
        verdict = "regress"
        notes.append(f"candidate regressed by {delta:.3f}; keeping baseline")
    else:
        verdict = "neutral"
        notes.append(f"delta {delta:+.3f} within tolerance; keeping baseline")

    if not dry_run and verdict == "promote":
        if traces:
            state["last_checkpoint_ts"] = max(
                (steps[-1].ts if steps else last_ts) for steps in traces
            )
        history = list(state.get("history") or [])
        history.append(
            {
                "at": time.time(),
                "candidate_tag": candidate_tag,
                "candidate_rate": candidate_rate,
                "baseline_rate": baseline_rate,
                "delta": delta,
                "promoted": True,
            }
        )
        state["history"] = history[-50:]
        state["last_run_at"] = time.time()
        _save_state(state_path, state)

    return LoopReport(
        started_at=start,
        base_model=base_model,
        candidate_tag=candidate_tag,
        new_traces=new_count,
        sft_pairs_appended=appended,
        finetune_invoked=finetune_invoked,
        candidate_eval_success_rate=candidate_rate,
        baseline_eval_success_rate=baseline_rate,
        delta=round(delta, 3),
        verdict=verdict,
        notes=notes,
        duration_seconds=round(time.time() - start, 3),
    )


def cli() -> int:
    parser = argparse.ArgumentParser(description="Self-improvement loop for local agents")
    parser.add_argument("--base-model", required=True, help="Ollama base model tag")
    parser.add_argument("--candidate-tag", default=None, help="tag for the candidate model")
    parser.add_argument("--min-traces", type=int, default=MIN_TRACES_TO_RETRAIN)
    parser.add_argument("--promote-delta", type=float, default=PROMOTE_DELTA)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    report = run_loop(
        base_model=args.base_model,
        candidate_tag=args.candidate_tag,
        min_traces=args.min_traces,
        promote_delta=args.promote_delta,
        dry_run=args.dry_run,
    )
    print(json.dumps(report.to_dict(), indent=2, default=str))
    if report.verdict == "regress":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(cli())
