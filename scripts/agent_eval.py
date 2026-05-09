"""Lightweight tau-bench-style local agent eval.

Defines a small panel of scripted tasks with mocked tools. The eval
runs each task against an Ollama model, asserts on the resulting tool
sequence and final state, and reports per-axis metrics:

    * success_rate
    * avg_steps_to_success
    * tool_error_rate

Goal is *cheap and reproducible*, not comprehensive. Use this as the
gate in scripts/self_improve_loop.py — promote a fine-tune only if it
beats the frozen baseline on this panel.

Inspired by sierra-research/tau2-bench. No external dependencies.

Run::

    python scripts/agent_eval.py --model qwen2.5-coder:14b
    python scripts/agent_eval.py --model qwen2.5-coder:14b --output data/agent_space/autonomy/eval_baseline.json
    python scripts/agent_eval.py --model my-agent:2026-05-09 --compare data/agent_space/autonomy/eval_baseline.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

# Repo path bootstrap so we can reuse backend/models/ollama_client.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from models import ollama_client  # noqa: E402

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- mocked tools


@dataclass
class MockState:
    """Per-task in-memory tool state."""

    files: dict[str, str] = field(default_factory=dict)
    web_pages: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    tool_errors: int = 0


def _tool_read_file(state: MockState, args: dict[str, Any]) -> dict[str, Any]:
    path = str(args.get("path") or "")
    if path not in state.files:
        state.tool_errors += 1
        return {"success": False, "error": f"file '{path}' not found"}
    return {"success": True, "path": path, "content": state.files[path]}


def _tool_write_file(state: MockState, args: dict[str, Any]) -> dict[str, Any]:
    path = str(args.get("path") or "")
    content = str(args.get("content") or "")
    if not path:
        state.tool_errors += 1
        return {"success": False, "error": "empty path"}
    state.files[path] = content
    return {"success": True, "path": path}


def _tool_web_fetch(state: MockState, args: dict[str, Any]) -> dict[str, Any]:
    url = str(args.get("url") or "")
    if url not in state.web_pages:
        state.tool_errors += 1
        return {"success": False, "error": f"url '{url}' unreachable in mock"}
    return {"success": True, "url": url, "content": state.web_pages[url]}


def _tool_note(state: MockState, args: dict[str, Any]) -> dict[str, Any]:
    text = str(args.get("text") or "")
    state.notes.append(text)
    return {"success": True, "note_count": len(state.notes)}


MOCK_TOOLS: dict[str, Callable[[MockState, dict[str, Any]], dict[str, Any]]] = {
    "read_file": _tool_read_file,
    "write_file": _tool_write_file,
    "web_fetch": _tool_web_fetch,
    "note": _tool_note,
}


# ---------------------------------------------------------------- eval task


@dataclass
class EvalTask:
    name: str
    description: str
    initial_state: dict[str, Any]
    objective: str
    success_check: Callable[[MockState, list[dict[str, Any]]], bool]
    max_steps: int = 8


def _build_state(initial: dict[str, Any]) -> MockState:
    state = MockState()
    state.files = dict(initial.get("files") or {})
    state.web_pages = dict(initial.get("web_pages") or {})
    return state


# Minimal panel — extend as the platform grows.
TASKS: list[EvalTask] = [
    EvalTask(
        name="copy_readme_summary",
        description="Read README.md, summarize, write to summary.md",
        initial_state={
            "files": {
                "README.md": (
                    "# JimAI\nLocal-first AI workspace. Multi-agent orchestration. "
                    "Web research. Builder. Browser automation."
                )
            }
        },
        objective="Read README.md, then write a one-sentence summary to summary.md.",
        success_check=lambda s, calls: "summary.md" in s.files
        and len(s.files["summary.md"]) > 10
        and "JimAI" in s.files["summary.md"],
        max_steps=6,
    ),
    EvalTask(
        name="web_then_note",
        description="Fetch a url, store its key insight as a note",
        initial_state={
            "web_pages": {
                "https://example.com/policy": "Refunds available within 30 days of purchase. Use code REFUND2026."
            }
        },
        objective=(
            "Fetch https://example.com/policy. Take a note containing the refund window in days."
        ),
        success_check=lambda s, calls: any("30" in n for n in s.notes),
        max_steps=4,
    ),
    EvalTask(
        name="missing_file_recovery",
        description="Tries a nonexistent file; should write a stub instead",
        initial_state={"files": {}},
        objective=(
            "Read config.json. If it does not exist, create config.json with the content '{}'."
        ),
        success_check=lambda s, calls: s.files.get("config.json", "").strip() in {"{}", "{ }"},
        max_steps=4,
    ),
]


# ---------------------------------------------------------------- agent loop


REACT_SYSTEM = (
    "You are an autonomous agent. You have the following tools:\n"
    "  read_file(path): read file contents\n"
    "  write_file(path, content): write/overwrite a file\n"
    "  web_fetch(url): fetch a web page\n"
    "  note(text): record a short note\n"
    "  finish(reason): end the task\n\n"
    "Respond with EXACTLY one JSON object per turn, no prose:\n"
    "  {\"thought\": \"...\", \"action\": {\"tool\": \"...\", \"args\": {...}}}\n\n"
    "Stop when the objective is satisfied by calling tool 'finish'."
)


def _extract_first_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    text = text.strip()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        return None
    return None


@dataclass
class TaskResult:
    name: str
    success: bool
    steps_used: int
    tool_errors: int
    elapsed_seconds: float
    transcript: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def _run_task(model: str, task: EvalTask, *, temperature: float = 0.2) -> TaskResult:
    state = _build_state(task.initial_state)
    tool_calls: list[dict[str, Any]] = []
    transcript: list[dict[str, Any]] = [{"role": "system", "content": REACT_SYSTEM}]
    transcript.append({"role": "user", "content": f"Objective: {task.objective}"})

    started_at = time.time()
    success = False
    error_msg = ""
    steps = 0
    for step in range(task.max_steps):
        steps = step + 1
        prompt = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in transcript[-20:]
        ) + "\nASSISTANT:"
        try:
            raw = await asyncio.wait_for(
                ollama_client.generate_full(
                    model=model,
                    prompt=prompt,
                    temperature=temperature,
                    num_predict=256,
                ),
                timeout=30,
            )
        except Exception as exc:
            error_msg = f"model error at step {step}: {exc}"
            break
        transcript.append({"role": "assistant", "content": raw})
        parsed = _extract_first_json_object(raw or "")
        if not parsed:
            transcript.append({"role": "user", "content": "Invalid JSON. Respond with one JSON object."})
            continue
        action = parsed.get("action") or {}
        tool = str(action.get("tool") or "")
        args = action.get("args") or {}
        if not isinstance(args, dict):
            args = {}
        if tool == "finish":
            break
        if tool not in MOCK_TOOLS:
            transcript.append({
                "role": "user",
                "content": f"Tool '{tool}' is not available. Choose from: {sorted(MOCK_TOOLS)} or 'finish'.",
            })
            state.tool_errors += 1
            continue
        result = MOCK_TOOLS[tool](state, args)
        tool_calls.append({"tool": tool, "args": args, "result": result})
        transcript.append({"role": "user", "content": f"Tool result: {json.dumps(result)[:600]}"})
        if task.success_check(state, tool_calls):
            success = True
            break

    if not success and not error_msg:
        success = task.success_check(state, tool_calls)

    elapsed = time.time() - started_at
    return TaskResult(
        name=task.name,
        success=success,
        steps_used=steps,
        tool_errors=state.tool_errors,
        elapsed_seconds=round(elapsed, 3),
        transcript=transcript[-12:],
        error=error_msg,
    )


@dataclass
class EvalReport:
    model: str
    started_at: float
    duration_seconds: float
    success_rate: float
    avg_steps_to_success: float
    tool_error_rate: float
    results: list[TaskResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "results": [r.to_dict() for r in self.results],
        }


async def run_eval(model: str, *, tasks: list[EvalTask] | None = None) -> EvalReport:
    panel = list(tasks or TASKS)
    started_at = time.time()
    results: list[TaskResult] = []
    for task in panel:
        result = await _run_task(model, task)
        results.append(result)
        logger.info(
            "eval %s success=%s steps=%d errors=%d", task.name, result.success, result.steps_used, result.tool_errors
        )
    n = len(results)
    successes = [r for r in results if r.success]
    success_rate = len(successes) / max(1, n)
    avg_steps = sum(r.steps_used for r in successes) / max(1, len(successes))
    total_steps = max(1, sum(r.steps_used for r in results))
    tool_error_rate = sum(r.tool_errors for r in results) / total_steps
    return EvalReport(
        model=model,
        started_at=started_at,
        duration_seconds=round(time.time() - started_at, 3),
        success_rate=round(success_rate, 3),
        avg_steps_to_success=round(avg_steps, 2),
        tool_error_rate=round(tool_error_rate, 3),
        results=results,
    )


def _compare(report: EvalReport, baseline_path: Path) -> dict[str, Any]:
    if not baseline_path.exists():
        return {"baseline_exists": False, "verdict": "no baseline to compare against"}
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"baseline_exists": False, "verdict": "could not read baseline"}
    base_rate = float(baseline.get("success_rate") or 0.0)
    delta = report.success_rate - base_rate
    if delta > 0.05:
        verdict = "promote"
    elif delta < -0.05:
        verdict = "regress"
    else:
        verdict = "neutral"
    return {
        "baseline_exists": True,
        "baseline_success_rate": base_rate,
        "candidate_success_rate": report.success_rate,
        "delta": round(delta, 3),
        "verdict": verdict,
    }


def cli() -> int:
    parser = argparse.ArgumentParser(description="Run lightweight agent eval")
    parser.add_argument("--model", required=True, help="Ollama model tag")
    parser.add_argument("--output", help="Write JSON report to this path")
    parser.add_argument("--compare", help="Path to a baseline report to compare against")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    report = asyncio.run(run_eval(args.model))
    print(json.dumps(report.to_dict(), indent=2, default=str))

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
        print(f"\nWrote report to {out}")

    if args.compare:
        verdict = _compare(report, Path(args.compare))
        print("\nComparison:", json.dumps(verdict, indent=2))
        if verdict.get("verdict") == "regress":
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(cli())
