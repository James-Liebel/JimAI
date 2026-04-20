"""Data science agent — EDA, ML model suggestion, statistical testing."""

import logging
import re

from models import ollama_client
from models.router import get_current_model, set_current_model
from config.models import MODEL_ROUTES, get_speed_mode
from config.inference_params import get_inference_params
from config.ds_context import DATA_SCIENCE_CONTEXT, DS_CODE_STANDARDS
from tools import python_exec

logger = logging.getLogger(__name__)


async def run(task: str, session_id: str = "default") -> dict:
    """Execute a data science task: EDA, ML suggestion, or statistical test.

    Returns {code, outputs, plots, assumptions_checked, interpretation}.
    """
    config = MODEL_ROUTES["code"]

    current = get_current_model()
    if current and current != config.model:
        await ollama_client.unload_model(current)
    set_current_model(config.model)

    system = (
        f"{config.system_prompt}\n\n"
        f"{DATA_SCIENCE_CONTEXT}\n\n"
        f"{DS_CODE_STANDARDS}\n\n"
        "You are a data science agent. Generate executable Python code "
        "to accomplish the user's data science task. The code should be "
        "self-contained. Use pandas, numpy, scipy, sklearn as needed. "
        "Print all results to stdout. For plots, save to a temp file "
        "and print the path."
    )

    params = get_inference_params("data", get_speed_mode())
    response = await ollama_client.generate_full(
        model=config.model,
        prompt=task,
        system=system,
        temperature=params.get("temperature", 0.1),
        num_ctx=params.get("num_ctx"),
        num_predict=params.get("num_predict"),
        num_batch=params.get("num_batch"),
        repeat_penalty=params.get("repeat_penalty", 1.1),
    )

    code_blocks = re.findall(r"```(?:python|py)?\n(.*?)```", response, re.DOTALL)
    code = "\n\n".join(code_blocks) if code_blocks else ""

    outputs = ""
    plots: list[str] = []
    assumptions_checked = "assumption" in task.lower() or "test" in task.lower()

    if code:
        exec_result = await python_exec.execute(code, timeout=60)
        outputs = exec_result.get("stdout", "")
        if exec_result.get("stderr"):
            outputs += f"\nStderr: {exec_result['stderr']}"

    explanation = re.sub(r"```.*?```", "", response, flags=re.DOTALL).strip()

    return {
        "code": code,
        "outputs": outputs,
        "plots": plots,
        "assumptions_checked": assumptions_checked,
        "interpretation": explanation,
    }
