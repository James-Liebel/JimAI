"""Orchestrator agent — classifies tasks, routes to specialist agents, synthesizes results."""

import json
import logging

from models import ollama_client
from models.router import get_current_model, set_current_model
from config.models import MODEL_ROUTES

logger = logging.getLogger(__name__)


async def classify_task(task: str) -> list[dict]:
    """Use the chat model to decompose a task into subtasks with agent assignments.

    Returns [{task: str, agent: str, depends_on: list[int]}]
    """
    config = MODEL_ROUTES["chat"]
    current = get_current_model()
    if current and current != config.model:
        await ollama_client.unload_model(current)
    set_current_model(config.model)

    prompt = (
        "You are a task planner. Decompose this task into subtasks.\n"
        "Available agents: math, code, research, writing\n"
        "Return a JSON array where each object has:\n"
        '  - "task": the subtask description\n'
        '  - "agent": which agent to use (math, code, research, or writing)\n'
        '  - "depends_on": array of indices of subtasks that must complete first\n\n'
        f"Task: {task}\n\n"
        "Return ONLY valid JSON, no explanation."
    )

    response = await ollama_client.generate_full(
        model=config.model,
        prompt=prompt,
        temperature=0.3,
    )

    # Parse the JSON from response
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]

    try:
        subtasks = json.loads(text)
        if isinstance(subtasks, list):
            return subtasks
    except json.JSONDecodeError:
        logger.warning("Could not parse orchestrator response as JSON")

    # Fallback: single task using chat
    return [{"task": task, "agent": "chat", "depends_on": []}]


async def synthesize(task: str, results: dict[str, dict]) -> str:
    """Combine all agent results into a final coherent response."""
    config = MODEL_ROUTES["chat"]
    current = get_current_model()
    if current and current != config.model:
        await ollama_client.unload_model(current)
    set_current_model(config.model)

    # Build context from results
    result_parts: list[str] = []
    for agent_name, result in results.items():
        if isinstance(result, dict):
            # Extract the main content from the result
            content = result.get("answer") or result.get("draft") or result.get("summary") or result.get("code") or str(result)
            result_parts.append(f"[{agent_name} agent result]:\n{content}")

    context = "\n\n---\n\n".join(result_parts)

    synthesis_prompt = (
        f"Original task: {task}\n\n"
        f"Agent results:\n{context}\n\n"
        "Synthesize these results into a single, coherent, well-structured response."
    )

    return await ollama_client.generate_full(
        model=config.model,
        prompt=synthesis_prompt,
        system="Combine the specialist agent outputs into a clear, unified answer.",
        temperature=0.5,
    )
