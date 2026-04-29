"""
Self-consistency checking for quantitative domains (math, finance).

Generates N independent solutions at slightly different temperatures,
extracts final answers, picks the majority. When solutions cluster,
confidence in correctness is significantly higher than single-shot.

N=1 in Fast mode (disabled), N=3 in Balanced, N=5 in Deep.
Used for math and finance — both have silent, consequential errors.
Code correctness is verified separately by actually running it.
"""

import math
import re
from typing import Optional

from config.models import get_config, get_speed_mode, SpeedMode
from models import ollama_client


_CURRENCY_PAT = re.compile(r"[-+]?\$\s*([\d,]+(?:\.\d+)?)")
_PERCENT_PAT = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*%")
_BPS_PAT = re.compile(r"([-+]?\d+(?:\.\d+)?)\s*bps\b", re.I)


def _canonicalize_answer(raw: str, domain: str) -> tuple[str, Optional[float]]:
    """Return (display_form, numeric_value_or_None). Numeric form drives clustering."""
    s = raw.strip()
    cleaned = s.replace(",", "").replace("$", "").rstrip("%").strip()
    try:
        return s, float(cleaned)
    except ValueError:
        pass
    if domain == "finance":
        for pat in (_CURRENCY_PAT, _PERCENT_PAT, _BPS_PAT):
            m = pat.search(s)
            if m:
                try:
                    return s, float(m.group(1).replace(",", ""))
                except ValueError:
                    continue
    return s, None


def _numeric_match(a: float, b: float, domain: str) -> bool:
    if domain == "finance":
        return math.isclose(a, b, abs_tol=0.01, rel_tol=1e-4)
    return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9)


async def self_consistent_quant(question: str, domain: str = "math") -> dict:
    """
    Run self-consistency sampling for a math problem.

    Returns:
        answer: str — best solution (majority answer's solution)
        confidence: "high" | "medium" | "low" | "single_shot"
        agreement_rate: float — fraction of samples that agree
        n_samples: int — number of samples generated
        disagreements: list[str] — answers that differed from majority
    """
    mode = get_speed_mode()
    config = get_config(domain if domain in {"math", "finance"} else "math")
    model = config.model
    system = config.system_prompt

    if mode == SpeedMode.FAST:
        response = ""
        async for chunk in ollama_client.generate(
            model=model,
            prompt=question,
            system=system,
            stream=True,
            temperature=0.05,
            num_ctx=8192,
            num_batch=512,
        ):
            response += chunk
        return {
            "answer": response,
            "confidence": "single_shot",
            "agreement_rate": 1.0,
            "n_samples": 1,
            "disagreements": [],
        }

    n = 5 if mode == SpeedMode.DEEP else 3
    temps = [0.05, 0.1, 0.15, 0.2, 0.08][:n]

    solutions = []
    for i in range(n):
        response = ""
        async for chunk in ollama_client.generate(
            model=model,
            prompt=f"Solve this problem independently. Show your full work:\n\n{question}",
            system=system,
            stream=True,
            temperature=temps[i],
            num_ctx=16384 if mode == SpeedMode.BALANCED else 32768,
            num_batch=1024 if mode == SpeedMode.BALANCED else 2048,
        ):
            response += chunk
        solutions.append(response)

    final_answers = [_extract_final_answer(s) for s in solutions]
    canonical: list[tuple[Optional[str], Optional[float]]] = [
        _canonicalize_answer(a, domain) if a is not None else (None, None)
        for a in final_answers
    ]
    valid = [c for c in canonical if c[0] is not None]

    if not valid:
        return {
            "answer": solutions[0],
            "confidence": "low",
            "agreement_rate": 0.0,
            "n_samples": n,
            "disagreements": [],
            "note": "Could not extract comparable final answers for consistency check",
        }

    # Cluster by numeric equivalence when both have a number, else by string equality.
    clusters: list[dict] = []
    for sol, (display, num) in zip(solutions, canonical):
        if display is None:
            continue
        placed = False
        for c in clusters:
            if num is not None and c["num"] is not None and _numeric_match(num, c["num"], domain):
                c["members"].append((sol, display))
                placed = True
                break
            if num is None and c["num"] is None and c["key"] == display:
                c["members"].append((sol, display))
                placed = True
                break
        if not placed:
            clusters.append({"key": display, "num": num, "members": [(sol, display)]})

    clusters.sort(key=lambda c: len(c["members"]), reverse=True)
    majority = clusters[0]
    majority_count = len(majority["members"])
    agreement_rate = majority_count / n
    best_solution = majority["members"][0][0]
    majority_answer = majority["key"]
    disagreements = [d for c in clusters[1:] for _s, d in c["members"]]

    confidence = (
        "high"
        if agreement_rate >= 0.8
        else ("medium" if agreement_rate >= 0.6 else "low")
    )

    return {
        "answer": best_solution,
        "confidence": confidence,
        "agreement_rate": agreement_rate,
        "majority_answer": majority_answer,
        "n_samples": n,
        "disagreements": disagreements,
    }


async def self_consistent_math(question: str) -> dict:
    """Back-compat alias — use self_consistent_quant(question, domain='math')."""
    return await self_consistent_quant(question, domain="math")


def _extract_final_answer(text: str) -> Optional[str]:
    """Extract the final numerical/symbolic answer from a math solution."""
    boxed = re.findall(r"\\boxed\{([^}]+)\}", text)
    if boxed:
        return boxed[-1].strip()

    for pattern in [
        r"(?:answer is|result is|equals?)\s*([-\d.,/π√e\^{}]+)",
        r"(?:therefore|thus|so)[,\s]+[^=\n]*=\s*([-\d.,/π√e\^{}]+)",
    ]:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            return matches[-1].strip()

    return None
