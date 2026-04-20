"""
Model-as-judge quality verification.

Architecture:
- Cross-model rule: judge is NEVER the same model that generated the response
- Cascaded: fast judge (qwen3:8b) first; escalate to deep judge for math/finance
- Judge always uses temperature=0.1 for evaluation consistency
- Returns structured JudgeVerdict — never prose
- Fast mode: judging skipped entirely (speed is the contract)
"""

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from config.models import get_speed_mode, SpeedMode
from models import ollama_client


class JudgeConfidence(str, Enum):
    HIGH = "high"    # confident verdict
    MEDIUM = "medium"  # some uncertainty — show but flag
    LOW = "low"     # judge itself uncertain — surface to user


@dataclass
class JudgeVerdict:
    passed: bool
    confidence: JudgeConfidence
    issues: list[str]
    suggestions: list[str]
    revised_response: Optional[str]
    judge_model: str
    judge_reasoning: str


JUDGE_RUBRICS = {
    "math": """Evaluate this mathematical response:
1. CORRECTNESS: Are all equations, calculations, and logical steps correct?
   Check arithmetic, algebra, calculus operations, statistical formulas.
2. COMPLETENESS: Are all required steps shown? Are assumptions stated?
3. VERIFICATION: Has the result been checked against boundary conditions?
4. FORMAT: Is math in LaTeX? Steps numbered? Plain-English summary present?
5. PRECISION: Are claims appropriately precise?

Flag specifically: mathematical errors, skipped non-trivial steps,
unstated assumptions, missing verification, confused notation.""",

    "code": """Evaluate this code response:
1. CORRECTNESS: Does the code actually solve the stated problem?
   Check logic, edge cases, off-by-one errors, type errors.
2. SAFETY: Unhandled exceptions? Security issues?
3. DATA SCIENCE: No DataFrame row iteration? Seeds set? Pipeline prevents leakage?
   Assumptions checked before statistical tests?
4. QUALITY: Type annotations? Docstring? Named constants?

Flag specifically: logic errors, missing error handling, data leakage,
DataFrame row iteration, missing type annotations, magic numbers.""",

    "finance": """Evaluate this financial analysis response:
1. METHODOLOGY: Is the valuation approach appropriate?
2. ASSUMPTIONS: Are key assumptions stated explicitly and reasonable?
3. ARITHMETIC: Are all calculations correct? WACC, multiples, growth rates.
4. COMPLETENESS: Is a range given, not a point estimate? Key risks identified?
5. STANDARD: Would a CFA analyst find this rigorous?

Flag specifically: wrong formulas, unstated assumptions, missing sensitivity
analysis, point estimates instead of ranges, missing risk discussion,
confusing enterprise value with equity value.""",

    "general": """Evaluate this response:
1. ACCURACY: Are factual claims correct and well-supported?
2. RELEVANCE: Does it answer the question actually asked?
3. COMPLETENESS: Are important aspects addressed?
4. REASONING: Is the logic sound? Are conclusions supported?

Flag specifically: factual errors, failure to address the question,
logical gaps, unsupported conclusions, contradictions.""",
}

JUDGE_TEMPLATE = """You are a strict quality evaluator. Your job is to find problems
in AI-generated responses — not to praise them.

ORIGINAL QUESTION:
{question}

RESPONSE TO EVALUATE:
{response}

EVALUATION RUBRIC:
{rubric}

Think through each criterion carefully. Identify specific problems with precise
locations (e.g., "step 3: wrong sign in integration" not "math errors").

Respond ONLY in this exact JSON format — no markdown, no preamble:
{{
  "reasoning": "your step-by-step evaluation thinking",
  "passed": true or false,
  "confidence": "high" or "medium" or "low",
  "issues": ["specific issue 1", "specific issue 2"],
  "suggestions": ["specific improvement 1", "specific improvement 2"],
  "revised_response": "corrected version if errors found, or null if passed"
}}

Be strict. "passed: true, confidence: high" means a domain expert finds no significant problems."""


def _select_judge_model(response_model: str, use_deep: bool) -> str:
    """Select judge model — never same as response model."""
    if response_model in ("qwen3:14b", "deepseek-r1:14b", "qwen2-math:7b-instruct"):
        return "qwen2.5-coder:14b" if use_deep else "qwen3:8b"
    elif response_model in ("qwen2.5-coder:14b", "qwen2.5-coder:7b", "qwen2.5-coder:3b"):
        return "qwen3:14b" if use_deep else "qwen3:8b"
    elif response_model == "qwen3:8b":
        return "qwen2.5-coder:14b" if use_deep else "qwen3:14b"
    elif response_model == "qwen2.5:32b-instruct-q3_k_s":
        return "qwen3:14b"
    else:
        return "qwen3:8b"


async def judge_response(
    question: str,
    response: str,
    response_model: str,
    domain: str,
    force_deep: bool = False,
) -> JudgeVerdict:
    """Judge a model response. Returns JudgeVerdict with structured findings."""
    use_deep = force_deep or domain in ("math", "finance")
    judge_model = _select_judge_model(response_model, use_deep)
    rubric = JUDGE_RUBRICS.get(domain, JUDGE_RUBRICS["general"])

    prompt = JUDGE_TEMPLATE.format(
        question=question,
        response=response,
        rubric=rubric,
    )

    raw = ""
    async for chunk in ollama_client.generate(
        model=judge_model,
        prompt=prompt,
        system="You are a strict quality evaluator. Return only valid JSON.",
        stream=True,
        temperature=0.1,
        num_ctx=8192,
    ):
        raw += chunk

    try:
        clean = raw.strip()
        if "```" in clean:
            parts = clean.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:]
                part = part.strip()
                if part.startswith("{"):
                    clean = part
                    break

        data = json.loads(clean)
        return JudgeVerdict(
            passed=bool(data.get("passed", True)),
            confidence=JudgeConfidence(data.get("confidence", "medium")),
            issues=data.get("issues", []),
            suggestions=data.get("suggestions", []),
            revised_response=data.get("revised_response"),
            judge_model=judge_model,
            judge_reasoning=data.get("reasoning", ""),
        )
    except (json.JSONDecodeError, ValueError, KeyError):
        return JudgeVerdict(
            passed=True,
            confidence=JudgeConfidence.LOW,
            issues=["Judge returned invalid output — could not evaluate"],
            suggestions=[],
            revised_response=None,
            judge_model=judge_model,
            judge_reasoning="JSON parse error",
        )


def should_judge(domain: str, speed_mode: str, message_length: int) -> bool:
    """
    Decide whether to run the judge.

    Always judges:  math, finance, code in Balanced/Deep with substantial responses
    Never judges:   fast mode (speed contract), short chat, tab completions

    Math and finance errors are silent and consequential — always verify.
    """
    if speed_mode == "fast":
        return False
    if domain in ("math", "finance"):
        return True
    if speed_mode == "deep":
        return True
    if domain == "code" and message_length > 100:
        return True
    return False
