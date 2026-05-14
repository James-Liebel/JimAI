"""Plan → draft → critique → revise pipeline for complex chat questions.

Chat-mode questions don't currently benefit from any quality-control loop —
the judge only runs for math/code/finance. This module fills that gap for
complex general questions by orchestrating three sequential LLM passes:

    1. PLAN     — decompose the question into the sub-questions that must be
                  answered, list assumptions to validate, and pick an answer
                  structure. Cheap fast pass (1 short call).
    2. DRAFT    — answer using the plan, with reasoning shown inline. Uses
                  the configured chat model and inference params.
    3. CRITIQUE — judge.py grades the draft against domain rubric. If the
                  judge produces a revised_response, swap it in.

The loop is opt-in per turn: chat.py calls run_complex_reasoning() only
when is_complex_question() returns True. Latency vs. quality trade-off is
managed by speed mode — turbo/fast skip the loop entirely.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from agents.judge import JudgeVerdict, judge_response
from config.models import SpeedMode, get_config, get_speed_mode
from models import ollama_client

logger = logging.getLogger(__name__)


# Heuristics for "this question is worth a reasoning loop".
# We err on the side of running the loop for anything that smells like
# multi-step reasoning, comparison, explanation, or open-ended exploration.
_COMPLEX_KEYWORDS = re.compile(
    r"\b(why|how come|explain|analy[sz]e|compare|contrast|trade-?off|"
    r"design|architect|propose|recommend|evaluate|pros and cons|"
    r"strategy|implication|consequence|root cause|justify|defend|"
    r"step.?by.?step|walk me through|break.*down|deep dive|"
    r"what would happen|what if|under what|when should|how should|"
    r"plan|approach|outline)\b",
    re.IGNORECASE,
)

_MULTI_QUESTION_HINT = re.compile(r"\?.*\?", re.DOTALL)


@dataclass
class ReasoningResult:
    answer: str
    plan: str
    critique: Optional[JudgeVerdict]
    revised: bool
    passes: int  # how many LLM calls were burnt (plan + draft + critique = 3 nominal)


def is_complex_question(message: str, *, domain: str = "chat") -> bool:
    """Decide whether a chat-mode message warrants the plan→draft→critique loop.

    True if the question is long, multi-part, or contains reasoning verbs. Short
    factual questions ("what time is it", "what's pi") fall through to single-shot
    so simple lookups stay fast.
    """
    text = (message or "").strip()
    if not text:
        return False
    # Long messages are almost always layered tasks.
    if len(text) >= 220:
        return True
    if _MULTI_QUESTION_HINT.search(text):
        return True
    if _COMPLEX_KEYWORDS.search(text):
        return True
    # If the user pasted code/data and asked a question about it, treat as complex.
    if "```" in text and len(text) > 80:
        return True
    return False


def should_run_reasoning(domain: str, message: str) -> bool:
    """Speed-mode aware gate. Turbo/fast never reason — the speed contract wins.
    Math/finance already have self_consistent_quant + judge; we don't double-up.
    """
    mode = get_speed_mode()
    if mode in {SpeedMode.TURBO, SpeedMode.FAST}:
        return False
    if domain in {"math", "finance"}:
        return False
    return is_complex_question(message, domain=domain)


_PLAN_SYSTEM = (
    "You are a planning assistant. For the user's question, produce a tight "
    "execution plan the answering model will follow. Be concise — plans over "
    "180 words waste budget. Output only the plan, nothing else."
)

_PLAN_PROMPT_TEMPLATE = """Question:
{question}

Produce a plan in this exact shape, no extra prose:

SUBQUESTIONS:
- (each sub-question that must be answered, max 5)

ASSUMPTIONS TO VALIDATE:
- (each assumption baked into the question, max 4)

ANSWER STRUCTURE:
- (the section ordering the final answer should follow, max 6 bullets)

KNOWN FAILURE MODES:
- (specific mistakes a careless answer would make on this question, max 3)
"""


_DRAFT_SYSTEM_ADDENDUM = (
    "\n\n## Reasoning plan (follow this)\n{plan}\n\n"
    "Apply the plan above. Validate the listed assumptions before stating "
    "conclusions. Address every subquestion. Avoid the listed failure modes."
)


async def _make_plan(question: str, *, model: str) -> str:
    """Cheap one-shot plan generation. Falls back to empty plan on failure
    so the draft step is never blocked."""
    try:
        plan = await ollama_client.generate_full(
            model=model,
            prompt=_PLAN_PROMPT_TEMPLATE.format(question=question[:4000]),
            system=_PLAN_SYSTEM,
            temperature=0.2,
            num_ctx=4096,
            num_predict=400,
            repeat_penalty=1.1,
        )
        return (plan or "").strip()
    except Exception as exc:
        logger.debug("reasoner.plan failed: %s", exc)
        return ""


def augment_system_prompt_with_plan(system_prompt: str, plan: str) -> str:
    """Inject the reasoning plan into the existing system prompt.

    The draft pass uses the configured chat-model system prompt (CHAT_PROMPT_BALANCED
    or similar) — we don't replace it, we append the plan so the model still
    benefits from its persona/standards while now also following the plan.
    """
    if not plan:
        return system_prompt
    return f"{system_prompt}{_DRAFT_SYSTEM_ADDENDUM.format(plan=plan[:2400])}"


async def critique_and_revise(
    question: str,
    draft_response: str,
    *,
    response_model: str,
    domain: str = "general",
) -> Optional[JudgeVerdict]:
    """Run the judge over a drafted answer. Returns the verdict (with possibly
    a revised_response). Caller decides whether to surface the revision.

    The judge always uses a different model than the drafter, so this catches
    blind spots the original model would silently miss (e.g., hallucinated
    citations, contradiction between paragraphs, missing edge cases).
    """
    try:
        verdict = await judge_response(
            question=question,
            response=draft_response,
            response_model=response_model,
            domain=domain,
        )
        return verdict
    except Exception as exc:
        logger.debug("reasoner.critique failed: %s", exc)
        return None


async def plan_for(question: str) -> str:
    """Public helper — the caller (chat.py) makes the plan first, then uses
    augment_system_prompt_with_plan to fold it into the draft system prompt.
    Returning the raw plan separately lets the UI/routing surface it for
    transparency."""
    chat_cfg = get_config("chat")
    return await _make_plan(question, model=chat_cfg.model)
