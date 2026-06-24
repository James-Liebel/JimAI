"""Stream chat and tasks for a single agent with skills context."""

import json
from typing import AsyncGenerator

from agent_workspace.context import build_agent_context
from agent_workspace.models import Agent
from models import ollama_client


async def stream_agent_chat(
    agent: Agent,
    user_message: str,
    history: list[dict] | None = None,
    extra_shared_skills: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    """Yield SSE data lines for one assistant reply."""
    system = build_agent_context(agent, extra_shared_paths=extra_shared_skills)
    # Simple history: prepend as text block if present
    prompt = user_message
    if history:
        lines = []
        for m in history[-20:]:
            role = m.get("role", "")
            content = (m.get("content") or "").strip()
            if content:
                lines.append(f"{role.upper()}: {content}")
        if lines:
            prompt = "Prior conversation:\n" + "\n".join(lines) + "\n\nUser: " + user_message

    async for chunk in ollama_client.generate(
        model=agent.model,
        prompt=prompt,
        system=system,
        stream=True,
        temperature=0.7,
        num_ctx=16384,
    ):
        yield f"data: {json.dumps({'text': chunk, 'done': False, 'model': agent.model})}\n\n"
    yield f"data: {json.dumps({'text': '', 'done': True, 'model': agent.model})}\n\n"


async def run_agent_task(
    agent: Agent,
    task: str,
    extra_shared_skills: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    """Autonomous-style task: one long completion with skills context."""
    system = build_agent_context(agent, extra_shared_paths=extra_shared_skills)
    prompt = (
        "Complete the following task thoroughly. Show your work and produce a clear final answer.\n\n"
        f"TASK:\n{task}"
    )
    async for chunk in ollama_client.generate(
        model=agent.model,
        prompt=prompt,
        system=system,
        stream=True,
        temperature=0.5,
        # 16K, not 32K: at 32K a 14B's weights (~9GB) + KV cache (~6GB) overflow a
        # 16GB GPU, so Ollama spills layers to CPU (100% CPU, model stuck loaded).
        # 16K keeps the run fully on-GPU. Raise only with KV-cache quantization.
        num_ctx=16384,
    ):
        yield f"data: {json.dumps({'text': chunk, 'done': False, 'model': agent.model, 'type': 'task'})}\n\n"
    yield f"data: {json.dumps({'text': '', 'done': True, 'model': agent.model, 'type': 'task'})}\n\n"
