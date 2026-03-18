"""
Self-consistency checking for math.

Generates N independent solutions at slightly different temperatures,
extracts final answers, picks the majority. When solutions cluster,
confidence in correctness is significantly higher than single-shot.

N=1 in Fast mode (disabled), N=3 in Balanced, N=5 in Deep.
Only used for math — code correctness is verified by actually running it.
"""

import re
from collections import Counter
from typing import Optional

from config.models import get_config, get_speed_mode, SpeedMode
from models import ollama_client


async def self_consistent_math(question: str) -> dict:
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
    config = get_config("math")
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
        ):
            response += chunk
        solutions.append(response)

    final_answers = [_extract_final_answer(s) for s in solutions]
    valid_answers = [a for a in final_answers if a is not None]

    if not valid_answers:
        return {
            "answer": max(solutions, key=len),
            "confidence": "low",
            "agreement_rate": 0.0,
            "n_samples": n,
            "disagreements": [],
            "note": "Could not extract comparable final answers for consistency check",
        }

    counts = Counter(valid_answers)
    majority_answer, majority_count = counts.most_common(1)[0]
    agreement_rate = majority_count / n

    best_solution = next(
        s for s, a in zip(solutions, final_answers) if a == majority_answer
    )

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
        "disagreements": [a for a in valid_answers if a != majority_answer],
    }


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
