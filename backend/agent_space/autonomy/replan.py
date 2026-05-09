"""Mid-run goal re-evaluation.

After each subagent finishes, evaluate whether the original plan is still
valid given new observations. Implements Magentic-One's "Progress Ledger"
pattern: a single Orchestrator maintains running notes about what worked,
what didn't, and reassigns subtasks when workers stall.

Decision shape:
    {
        "decision": "continue" | "replan" | "abort",
        "reason": "...",
        "patches": [
            {"op": "drop", "task_index": 2},
            {"op": "insert_after", "task_index": 1, "task": {...}},
        ],
        "confidence": 0.0..1.0,
    }
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from models import ollama_client

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen2.5-coder:14b"


@dataclass
class ReplanDecision:
    decision: str  # "continue" | "replan" | "abort"
    reason: str
    patches: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.5
    raw: str = ""


def _extract_first_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    # Greedy first pass — direct parse.
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


class ReplanEngine:
    """Asks an LLM whether the plan still fits, returns a structured decision."""

    def __init__(self, *, model: str = DEFAULT_MODEL, max_replans: int = 3) -> None:
        self.model = model
        self.max_replans = int(max_replans)

    async def evaluate(
        self,
        *,
        objective: str,
        plan: list[dict[str, Any]],
        completed: list[dict[str, Any]],
        last_result: dict[str, Any] | None,
        replans_used: int = 0,
        model: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> ReplanDecision:
        if replans_used >= self.max_replans:
            return ReplanDecision(
                decision="continue",
                reason=f"replan budget exhausted ({replans_used}/{self.max_replans})",
                confidence=0.9,
            )
        plan_text = json.dumps(plan or [], ensure_ascii=False, indent=2)[:4000]
        completed_text = json.dumps(completed or [], ensure_ascii=False, indent=2)[:4000]
        last_text = json.dumps(last_result or {}, ensure_ascii=False, indent=2)[:2000]
        prompt = (
            "You are an orchestrator deciding whether the current plan should change.\n"
            "Review the objective, the original plan, what has completed, and the latest result.\n"
            "Return STRICT JSON ONLY with this shape:\n"
            "{\n"
            '  "decision": "continue" | "replan" | "abort",\n'
            '  "reason": "1-2 sentences",\n'
            '  "patches": [],   // when replanning, list patch ops\n'
            '  "confidence": 0.0..1.0\n'
            "}\n"
            "\n"
            "Patch ops are objects with one of these shapes:\n"
            '  {"op": "drop", "task_index": <int>}\n'
            '  {"op": "insert_after", "task_index": <int>, "task": {"task": "...", "agent": "..."}}\n'
            '  {"op": "replace", "task_index": <int>, "task": {"task": "...", "agent": "..."}}\n'
            "\n"
            "Decision rubric:\n"
            "- continue: plan still fits, do not change anything.\n"
            "- replan: at least one patch is needed (e.g. evidence shows a step is wrong).\n"
            "- abort: objective is no longer achievable or has been satisfied.\n"
            "\n"
            f"Objective:\n{objective[:1500]}\n\n"
            f"Original plan:\n{plan_text}\n\n"
            f"Completed steps:\n{completed_text}\n\n"
            f"Last result:\n{last_text}\n"
        )
        chosen = (model or self.model).strip()
        try:
            raw = await asyncio.wait_for(
                ollama_client.generate_full(
                    model=chosen,
                    prompt=prompt,
                    temperature=0.2,
                    num_predict=512,
                ),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            return ReplanDecision(
                decision="continue",
                reason="replan evaluator timed out",
                confidence=0.4,
            )
        except Exception as exc:
            logger.debug("Replan call failed: %s", exc)
            return ReplanDecision(
                decision="continue",
                reason=f"replan call error: {exc}",
                confidence=0.3,
            )
        parsed = _extract_first_json_object(raw or "")
        if parsed is None:
            return ReplanDecision(
                decision="continue",
                reason="replan output was not valid JSON",
                confidence=0.3,
                raw=str(raw or "")[:1000],
            )
        decision = str(parsed.get("decision") or "continue").lower().strip()
        if decision not in {"continue", "replan", "abort"}:
            decision = "continue"
        patches_raw = parsed.get("patches") or []
        patches: list[dict[str, Any]] = []
        if isinstance(patches_raw, list):
            for row in patches_raw:
                if not isinstance(row, dict):
                    continue
                op = str(row.get("op") or "").strip().lower()
                if op not in {"drop", "insert_after", "replace"}:
                    continue
                patches.append(
                    {
                        "op": op,
                        "task_index": int(row.get("task_index") or 0),
                        "task": dict(row.get("task") or {}),
                    }
                )
        confidence_raw = parsed.get("confidence")
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))
        return ReplanDecision(
            decision=decision,
            reason=str(parsed.get("reason") or "")[:600],
            patches=patches,
            confidence=confidence,
            raw=str(raw or "")[:2000],
        )

    @staticmethod
    def apply_patches(plan: list[dict[str, Any]], patches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply replan patches to a plan, returning a new list. Patches are applied
        in reverse index order so earlier indices remain stable."""
        if not patches:
            return list(plan)
        new_plan = list(plan)
        sorted_patches = sorted(
            patches,
            key=lambda p: int(p.get("task_index") or 0),
            reverse=True,
        )
        for patch in sorted_patches:
            op = str(patch.get("op") or "").strip().lower()
            idx = int(patch.get("task_index") or 0)
            task = patch.get("task") or {}
            if op == "drop":
                if 0 <= idx < len(new_plan):
                    new_plan.pop(idx)
            elif op == "replace":
                if 0 <= idx < len(new_plan) and isinstance(task, dict) and task:
                    new_plan[idx] = dict(task)
            elif op == "insert_after":
                if isinstance(task, dict) and task:
                    insert_at = max(0, min(idx + 1, len(new_plan)))
                    new_plan.insert(insert_at, dict(task))
        return new_plan
