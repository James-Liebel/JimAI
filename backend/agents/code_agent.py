"""Code agent — writes, tests, and optionally commits code."""

import logging
import re

from models import ollama_client
from models.router import get_current_model, set_current_model
from config.models import MODEL_ROUTES
from tools import python_exec, git_tool, file_tool

logger = logging.getLogger(__name__)

MAX_FIX_ITERATIONS = 5


async def run(task: str, file_context: str = "", commit: bool = False) -> dict:
    """Execute a coding task with iterative testing and optional git commit.

    Returns {code, explanation, test_results, committed, iterations}.
    """
    config = MODEL_ROUTES["code"]
    iterations = 0

    # VRAM management
    current = get_current_model()
    if current and current != config.model:
        await ollama_client.unload_model(current)
    set_current_model(config.model)

    # Build prompt with file context if provided
    prompt = task
    if file_context:
        prompt = f"File context:\n```\n{file_context}\n```\n\nTask: {task}"

    response = await ollama_client.generate_full(
        model=config.model,
        prompt=prompt,
        system=config.system_prompt,
        temperature=config.temperature,
    )
    iterations += 1

    # Extract code blocks
    code_blocks = re.findall(r"```(?:python|py)?\n(.*?)```", response, re.DOTALL)
    code = "\n\n".join(code_blocks) if code_blocks else ""

    test_results: dict = {"success": True}

    # If we got code, try to run it
    if code:
        for attempt in range(MAX_FIX_ITERATIONS):
            exec_result = await python_exec.execute(code)
            test_results = exec_result
            iterations += 1

            if exec_result["success"]:
                break

            # Feed error back to model for a fix
            fix_prompt = (
                f"This code produced an error:\n```python\n{code}\n```\n\n"
                f"Error:\n{exec_result['stderr']}\n\n"
                f"Fix the code. Return only the corrected code."
            )
            fix_response = await ollama_client.generate_full(
                model=config.model,
                prompt=fix_prompt,
                system=config.system_prompt,
                temperature=config.temperature,
            )
            new_blocks = re.findall(
                r"```(?:python|py)?\n(.*?)```", fix_response, re.DOTALL
            )
            if new_blocks:
                code = "\n\n".join(new_blocks)
            response = fix_response

    # Handle commit if requested
    committed = False
    if commit and "commit" in task.lower():
        try:
            await git_tool.add(["."])
            msg = f"feat: {task[:50]}"
            await git_tool.commit(msg)
            committed = True
        except Exception as exc:
            logger.warning("Git commit failed: %s", exc)

    # Extract explanation (text outside code blocks)
    explanation = re.sub(r"```.*?```", "", response, flags=re.DOTALL).strip()

    return {
        "code": code,
        "explanation": explanation,
        "test_results": test_results,
        "committed": committed,
        "iterations": iterations,
    }
