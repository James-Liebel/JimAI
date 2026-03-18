"""Tab completion API — fast code completions via Ollama."""

import logging
import time

from fastapi import APIRouter
from pydantic import BaseModel

from models import ollama_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["completion"])

COMPLETION_MODEL = "qwen2.5-coder:7b"


class CompletionRequest(BaseModel):
    prefix: str
    context: str = ""
    language: str = "python"
    cursor_position: int = 0


class CompletionResponse(BaseModel):
    completions: list[str]
    model: str
    latency_ms: int


@router.post("/completion", response_model=CompletionResponse)
async def get_completion(req: CompletionRequest):
    """Return tab completions. Always uses qwen2.5-coder:7b for speed."""
    start = time.time()

    prompt = (
        f"Complete the following {req.language} code. "
        f"Return ONLY the completion text, no explanation.\n\n"
        f"Context:\n{req.context[-2000:]}\n\n"
        f"Complete after: {req.prefix}"
    )

    try:
        result = await ollama_client.generate_full(
            model=COMPLETION_MODEL,
            prompt=prompt,
            system="You are a code completion engine. Return ONLY the completion text. No markdown, no explanation.",
            temperature=0.05,
        )
        completion = result.strip()
        if completion.startswith("```"):
            lines = completion.split("\n")
            completion = "\n".join(lines[1:])
            if completion.endswith("```"):
                completion = completion[:-3]
        completions = [completion] if completion else []
    except Exception as e:
        logger.error("Completion failed: %s", e)
        completions = []

    latency = int((time.time() - start) * 1000)
    return CompletionResponse(
        completions=completions,
        model=COMPLETION_MODEL,
        latency_ms=latency,
    )


@router.post("/execute")
async def execute_code(req: dict):
    """Execute Python code and return output."""
    from tools.python_exec import execute

    code = req.get("code", "")
    if not code:
        return {"stdout": "", "stderr": "No code provided", "success": False}

    result = await execute(code)
    return result
