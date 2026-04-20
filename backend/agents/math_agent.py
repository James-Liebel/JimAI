"""Math agent — uses qwen2-math + SymPy for verified math solutions."""

import logging
import re

from models import ollama_client
from models.router import get_current_model, set_current_model
from config.models import MODEL_ROUTES, get_speed_mode
from config.inference_params import get_inference_params
from tools import math_tool

logger = logging.getLogger(__name__)

MAX_VERIFY_ATTEMPTS = 3


async def run(task: str) -> dict:
    """Execute a math task with model inference + symbolic verification.

    Returns {answer, latex, verified, steps, tool_results}.
    """
    config = MODEL_ROUTES["math"]
    steps: list[str] = []
    tool_results: list[dict] = []

    # VRAM management
    current = get_current_model()
    if current and current != config.model:
        await ollama_client.unload_model(current)
    set_current_model(config.model)

    params = get_inference_params("math", get_speed_mode())
    steps.append("Sending task to math model")
    response = await ollama_client.generate_full(
        model=config.model,
        prompt=task,
        system=config.system_prompt,
        temperature=params.get("temperature", config.temperature),
        num_ctx=params.get("num_ctx"),
        num_predict=params.get("num_predict"),
        num_batch=params.get("num_batch"),
        repeat_penalty=params.get("repeat_penalty", 1.05),
    )
    steps.append("Received model response")

    # Extract LaTeX expressions for verification
    display_math = re.findall(r"\$\$(.*?)\$\$", response, re.DOTALL)
    inline_math = re.findall(r"(?<!\$)\$([^$]+?)\$(?!\$)", response)
    all_exprs = display_math + inline_math

    verified = True
    for expr in all_exprs[:5]:  # verify up to 5 expressions
        expr_clean = expr.strip()
        if "=" in expr_clean:
            # Try to verify equations
            parts = expr_clean.split("=", 1)
            try:
                result = await math_tool.simplify_expr(
                    f"({parts[0]}) - ({parts[1]})"
                )
                tool_results.append({"expression": expr_clean, **result})
                if result["verified"]:
                    steps.append(f"Verified: {expr_clean[:50]}")
                else:
                    steps.append(f"Could not verify: {expr_clean[:50]}")
                    verified = False
            except Exception as exc:
                steps.append(f"Verification error for {expr_clean[:50]}: {exc}")
                verified = False

    # If verification failed, try to re-prompt
    if not verified and all_exprs:
        for attempt in range(MAX_VERIFY_ATTEMPTS - 1):
            steps.append(f"Re-prompting (attempt {attempt + 2})")
            retry_prompt = (
                f"The previous answer had verification issues. "
                f"Please re-solve carefully:\n{task}\n\n"
                f"Previous issues: {[r for r in tool_results if not r.get('verified')]}"
            )
            response = await ollama_client.generate_full(
                model=config.model,
                prompt=retry_prompt,
                system=config.system_prompt,
                temperature=params.get("temperature", config.temperature),
                num_ctx=params.get("num_ctx"),
                num_predict=params.get("num_predict"),
                num_batch=params.get("num_batch"),
                repeat_penalty=params.get("repeat_penalty", 1.05),
            )
            steps.append(f"Retry {attempt + 2} complete")
            break  # Accept the retry

    return {
        "answer": response,
        "latex": "\n".join(all_exprs) if all_exprs else "",
        "verified": verified,
        "steps": steps,
        "tool_results": tool_results,
    }
