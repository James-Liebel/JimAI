"""Multi-step task executor — plan, then execute each step with observation.

The single-pass reasoner (agents/reasoner.py) covers complex single-answer
questions: plan → draft → critique → revise, all in one streamed reply. That
is enough for "explain X" or "compare A and B", but it cannot handle tasks
that genuinely require sequential work — "design a strategy, then test it
against three counterexamples, then write a memo summarizing what survived".

This module fills that gap. It runs a small agent loop:

    PLAN     — decompose the task into ordered concrete steps + success criteria
    EXECUTE  — for each step: run a focused LLM pass with the running
               transcript visible, capture the observation, append to state
    REPLAN   — after each step, the planner sees the observation and may
               adjust the remaining steps (or terminate early if the task is
               already solved). Avoids dead-march execution of stale plans.
    SYNTHESIZE — turn the accumulated step outputs into one coherent final
                 answer using the chat persona.

It deliberately stays local-only and uses the same Ollama models that serve
chat, so we don't add a new dependency or cloud surface. Latency is the
trade-off: a 4-step task costs ~4× the time of a single answer.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from agents.judge import judge_response
from config.models import SpeedMode, get_config, get_speed_mode
from memory import db
from models import ollama_client

logger = logging.getLogger(__name__)

_MULTI_STEP_SLOT = "active_plan"
_MAX_STEPS = 6
_PER_STEP_TIMEOUT_SECONDS = 120.0

_MULTI_STEP_HINTS = re.compile(
    r"\b(then|after that|next|first.*then|step\s*\d+|step\s+(?:one|two|three|four|five|six)|"
    r"do.*and also|please also|in addition.*also|"
    r"design.*test|build.*evaluate|plan.*execute|"
    r"break.*down|multi[- ]step|several steps|"
    r"end[- ]to[- ]end|from scratch|all the way through)\b",
    re.IGNORECASE,
)

# Standalone inline-numbered-list pattern, ignoring line anchors so paragraph-
# style "1. do X. 2. do Y. 3. do Z." also routes as multi-step.
_INLINE_NUMBERED_LIST = re.compile(r"(?:(?<=\s)|^)\d+[.)]\s+\S", re.MULTILINE)


def is_multi_step_task(message: str) -> bool:
    """True if the task explicitly asks for multiple distinct stages.

    Conservative — only trips on clear signals. A user asking "explain X" is
    handled fine by the single-pass reasoner; we don't want to triple-bill
    every long question."""
    text = (message or "").strip()
    if not text:
        return False
    if len(text) >= 600:
        return True
    if _MULTI_STEP_HINTS.search(text):
        return True
    # Numbered list of requirements ("1.", "2.", "3." — anywhere in the text)
    # is a strong signal regardless of whether each is on its own line.
    if len(_INLINE_NUMBERED_LIST.findall(text)) >= 3:
        return True
    return False


def should_run_multi_step(domain: str, message: str) -> bool:
    """Speed-mode-aware gate. Balanced/Deep run multi-step; fast modes don't."""
    mode = get_speed_mode()
    if mode in {SpeedMode.TURBO, SpeedMode.FAST}:
        return False
    return is_multi_step_task(message)


@dataclass
class Step:
    index: int
    goal: str
    success_criteria: str
    output: str = ""
    elapsed_seconds: float = 0.0
    skipped: bool = False
    revised_plan_after: list[dict[str, str]] = field(default_factory=list)


@dataclass
class PlanState:
    task: str
    steps: list[Step]
    final_answer: str = ""
    completed: bool = False
    created_at: float = field(default_factory=time.time)


# ── Prompts ────────────────────────────────────────────────────────────────

_PLAN_SYSTEM = (
    "You break complex tasks into ordered, executable steps. Each step must "
    "be concrete enough that a focused worker model can complete it alone "
    "and produce a checkable output. Never plan more than 6 steps — if a task "
    "needs more, fold detail into a single step rather than fragmenting."
)

_PLAN_PROMPT = """Task:
{task}

Produce JSON only, no markdown:
{{
  "steps": [
    {{
      "goal": "one-sentence concrete goal for this step",
      "success_criteria": "how the worker knows the step is done"
    }}
  ]
}}

Rules:
- Max 6 steps. Less is better if the task allows.
- Each goal must be self-contained: don't say "continue from the previous step",
  state what the worker needs to do given what prior steps will have produced.
- Final step is usually a synthesis or write-up step.
- Skip steps that aren't actually needed for the task — empty plans are valid.
"""


_EXECUTE_SYSTEM_ADDENDUM = """

You are working through a multi-step plan. For THIS step only:
  GOAL: {goal}
  SUCCESS CRITERIA: {criteria}

Read the prior steps' outputs (below) as context. Produce only what THIS step
requires — do not pre-empt later steps. Be concrete and self-contained.
"""


_REPLAN_SYSTEM = (
    "You revise an in-progress execution plan based on what the worker has "
    "produced so far. Keep the plan tight — drop unneeded steps, refine "
    "remaining goals, or stop entirely if the task is already solved."
)

_REPLAN_PROMPT = """Original task:
{task}

Plan so far (executed steps with their outputs):
{transcript}

Remaining planned steps:
{remaining}

Produce JSON only:
{{
  "decision": "continue" | "stop",
  "remaining_steps": [
    {{ "goal": "...", "success_criteria": "..." }}
  ],
  "reason": "one-sentence why"
}}

Choose "stop" only if the executed steps' outputs already fully satisfy the
original task. Otherwise list the (possibly revised) remaining steps.
"""


_SYNTHESIS_SYSTEM = (
    "You produce the final, user-facing answer for a multi-step task. Use the "
    "step outputs as your evidence. Write directly to the user — do not say "
    '"Step 1 said…". The user does not need to see the plan; show them the '
    "result."
)

_SYNTHESIS_PROMPT_TEMPLATE = """Original task:
{task}

What the worker produced for each step:

{transcript}

Write the final answer that this work supports. Be direct and concrete.
Follow the user's original framing — if they asked for a memo, write a memo;
if they asked for code, output code; if they asked an analytical question,
answer it.
"""


# ── JSON-tolerant parsing ─────────────────────────────────────────────────


def _parse_json(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        text = brace.group(0)
    text = (
        text.replace("“", '"').replace("”", '"')
        .replace("‘", "'").replace("’", "'")
    )
    text = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


# ── Plan persistence (resumability) ────────────────────────────────────────


def _persist_state(session_id: str, state: PlanState) -> None:
    payload = {
        "task": state.task,
        "completed": state.completed,
        "created_at": state.created_at,
        "final_answer": state.final_answer,
        "steps": [
            {
                "index": s.index,
                "goal": s.goal,
                "success_criteria": s.success_criteria,
                "output": s.output,
                "elapsed_seconds": s.elapsed_seconds,
                "skipped": s.skipped,
            }
            for s in state.steps
        ],
    }
    try:
        db.write_user_slot(f"session:{session_id}", _MULTI_STEP_SLOT, payload)
    except Exception:
        logger.debug("multi_step: persist failed for %s", session_id, exc_info=True)


def load_state(session_id: str) -> dict[str, Any] | None:
    """Return the persisted plan state for a session, or None."""
    try:
        rec = db.read_user_slot(f"session:{session_id}", _MULTI_STEP_SLOT)
        if rec and isinstance(rec.get("data"), dict):
            return rec["data"]
    except Exception:
        pass
    return None


def clear_state(session_id: str) -> None:
    try:
        db.delete_user_slot(f"session:{session_id}", _MULTI_STEP_SLOT)
    except Exception:
        # db may not expose delete_user_slot — fall back to writing an empty record.
        try:
            db.write_user_slot(f"session:{session_id}", _MULTI_STEP_SLOT, {})
        except Exception:
            pass


# ── Core executor ──────────────────────────────────────────────────────────


async def _plan_steps(task: str, *, model: str) -> list[Step]:
    raw = await ollama_client.generate_full(
        model=model,
        prompt=_PLAN_PROMPT.format(task=task[:6000]),
        system=_PLAN_SYSTEM,
        temperature=0.2,
        num_ctx=8192,
        num_predict=900,
    )
    parsed = _parse_json(raw)
    steps_raw = (parsed or {}).get("steps") if parsed else None
    if not isinstance(steps_raw, list) or not steps_raw:
        # Fall back to a single "answer the task" step if planning fails.
        return [Step(index=0, goal=task[:240], success_criteria="task answered")]
    out: list[Step] = []
    for i, s in enumerate(steps_raw[:_MAX_STEPS]):
        if not isinstance(s, dict):
            continue
        goal = str(s.get("goal") or "").strip()
        crit = str(s.get("success_criteria") or "").strip()
        if not goal:
            continue
        out.append(Step(index=i, goal=goal, success_criteria=crit or "step output present"))
    return out or [Step(index=0, goal=task[:240], success_criteria="task answered")]


async def _execute_step(
    task: str,
    step: Step,
    prior_transcript: str,
    *,
    chat_model: str,
    chat_system_prompt: str,
) -> str:
    """Run one worker pass for a step. Worker sees the running transcript so
    it can build on earlier steps' outputs."""
    user_prompt = (
        f"Task overall: {task}\n\n"
        f"Prior step outputs:\n{prior_transcript or '(none yet — this is the first step)'}\n\n"
        f"Now perform step {step.index + 1}."
    )
    system = chat_system_prompt + _EXECUTE_SYSTEM_ADDENDUM.format(
        goal=step.goal,
        criteria=step.success_criteria,
    )
    try:
        async with asyncio.timeout(_PER_STEP_TIMEOUT_SECONDS):
            out = await ollama_client.generate_full(
                model=chat_model,
                prompt=user_prompt,
                system=system,
                temperature=0.4,
                num_ctx=16384,
                num_predict=2048,
            )
        return (out or "").strip()
    except asyncio.TimeoutError:
        return f"(step {step.index + 1} timed out after {_PER_STEP_TIMEOUT_SECONDS}s)"
    except Exception as exc:
        logger.debug("multi_step: step %d failed: %s", step.index, exc)
        return f"(step {step.index + 1} failed: {exc})"


async def _replan(
    task: str,
    completed: list[Step],
    remaining: list[Step],
    *,
    model: str,
) -> tuple[str, list[Step]]:
    """Decide whether to continue and (possibly) revise the remaining steps.

    Returns (decision, new_remaining_steps). decision in {"continue", "stop"}.
    """
    if not remaining:
        return "stop", []
    transcript = "\n\n".join(
        f"### Step {s.index + 1}: {s.goal}\n{s.output[:1600]}"
        for s in completed
    )
    remaining_dump = json.dumps(
        [{"goal": s.goal, "success_criteria": s.success_criteria} for s in remaining],
        ensure_ascii=False,
    )
    raw = await ollama_client.generate_full(
        model=model,
        prompt=_REPLAN_PROMPT.format(
            task=task[:4000],
            transcript=transcript[:8000],
            remaining=remaining_dump,
        ),
        system=_REPLAN_SYSTEM,
        temperature=0.2,
        num_ctx=16384,
        num_predict=600,
    )
    parsed = _parse_json(raw)
    if not parsed:
        return "continue", remaining
    decision = str(parsed.get("decision") or "continue").lower()
    if decision not in {"continue", "stop"}:
        decision = "continue"
    new_remaining_raw = parsed.get("remaining_steps") if isinstance(parsed.get("remaining_steps"), list) else None
    if not new_remaining_raw:
        return decision, remaining
    new_steps: list[Step] = []
    base = (completed[-1].index + 1) if completed else 0
    for i, s in enumerate(new_remaining_raw[:_MAX_STEPS]):
        if not isinstance(s, dict):
            continue
        goal = str(s.get("goal") or "").strip()
        crit = str(s.get("success_criteria") or "").strip()
        if not goal:
            continue
        new_steps.append(Step(index=base + i, goal=goal, success_criteria=crit))
    return decision, new_steps or remaining


async def _synthesize(
    task: str,
    completed: list[Step],
    *,
    chat_model: str,
    chat_system_prompt: str,
) -> AsyncGenerator[str, None]:
    transcript = "\n\n".join(
        f"### Step {s.index + 1}: {s.goal}\n{s.output}"
        for s in completed if not s.skipped
    )
    prompt = _SYNTHESIS_PROMPT_TEMPLATE.format(task=task[:4000], transcript=transcript[:14000])
    async for chunk in ollama_client.generate(
        model=chat_model,
        prompt=prompt,
        system=chat_system_prompt + "\n\n" + _SYNTHESIS_SYSTEM,
        stream=True,
        temperature=0.5,
        num_ctx=16384,
        num_predict=2048,
    ):
        yield chunk


async def run_multi_step(
    task: str,
    *,
    chat_system_prompt: str,
    session_id: str = "default",
) -> AsyncGenerator[dict[str, Any], None]:
    """Drive the full plan → execute → replan → synthesize loop.

    Yields event dicts so the caller (chat.py) can stream UI updates:
      {"type": "plan",        "steps": [...]}
      {"type": "step_start",  "index": N, "goal": "..."}
      {"type": "step_done",   "index": N, "output": "..."}
      {"type": "replan",      "decision": "continue|stop", "remaining": [...]}
      {"type": "synthesis_chunk", "text": "..."}
      {"type": "done",        "final_answer": "...", "steps": N}
    """
    chat_cfg = get_config("chat")
    chat_model = chat_cfg.model

    steps = await _plan_steps(task, model=chat_model)
    state = PlanState(task=task, steps=list(steps))
    _persist_state(session_id, state)
    yield {
        "type": "plan",
        "steps": [{"goal": s.goal, "success_criteria": s.success_criteria} for s in steps],
    }

    completed: list[Step] = []
    remaining: list[Step] = list(steps)

    while remaining:
        step = remaining.pop(0)
        step.index = len(completed)
        yield {"type": "step_start", "index": step.index, "goal": step.goal}

        t0 = time.time()
        prior_transcript = "\n\n".join(
            f"### Step {s.index + 1}: {s.goal}\n{s.output[:1600]}"
            for s in completed
        )
        step.output = await _execute_step(
            task, step, prior_transcript,
            chat_model=chat_model,
            chat_system_prompt=chat_system_prompt,
        )
        step.elapsed_seconds = time.time() - t0
        completed.append(step)
        state.steps = completed + remaining
        _persist_state(session_id, state)

        yield {"type": "step_done", "index": step.index, "output": step.output,
               "elapsed_seconds": step.elapsed_seconds}

        if remaining:
            decision, new_remaining = await _replan(
                task, completed, remaining, model=chat_model,
            )
            yield {
                "type": "replan",
                "decision": decision,
                "remaining": [{"goal": s.goal, "success_criteria": s.success_criteria}
                              for s in new_remaining],
            }
            if decision == "stop":
                remaining = []
                break
            remaining = new_remaining

    # Synthesis: stream the final user-facing answer.
    final_parts: list[str] = []
    async for chunk in _synthesize(
        task, completed,
        chat_model=chat_model,
        chat_system_prompt=chat_system_prompt,
    ):
        final_parts.append(chunk)
        yield {"type": "synthesis_chunk", "text": chunk}
    final = "".join(final_parts).strip()

    # Critique the synthesized answer just like the single-step reasoner does.
    try:
        verdict = await judge_response(
            question=task,
            response=final,
            response_model=chat_model,
            domain="general",
        )
        if verdict and not verdict.passed and verdict.revised_response:
            correction = str(verdict.revised_response).strip()
            yield {"type": "synthesis_chunk", "text": "\n\n---\n**Correction (judge):**\n" + correction}
            final = final + "\n\n---\n**Correction (judge):**\n" + correction
    except Exception:
        logger.debug("multi_step: synthesis critique skipped", exc_info=True)

    state.completed = True
    state.final_answer = final
    state.steps = completed
    _persist_state(session_id, state)

    yield {"type": "done", "final_answer": final, "steps": len(completed)}
