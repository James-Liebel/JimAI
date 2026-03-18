"""Agent execution graph — wires orchestrator + specialist agents into a runnable pipeline."""

import logging
from typing import AsyncGenerator

from agents import orchestrator, math_agent, code_agent, research_agent, writing_agent, data_agent
from models import ollama_client
from models.router import get_current_model

logger = logging.getLogger(__name__)

AGENT_RUNNERS = {
    "math": math_agent.run,
    "code": code_agent.run,
    "research": research_agent.run,
    "writing": writing_agent.run,
    "data": data_agent.run,
}


async def run_graph(task: str, session_id: str) -> AsyncGenerator[dict, None]:
    """Execute the full agent graph and yield status updates.

    Flow: orchestrator classifies → specialist agents execute → orchestrator synthesizes.
    """
    # Step 1: Classify the task
    yield {
        "agent": "orchestrator",
        "step": "Analyzing task and planning subtasks",
        "status": "running",
    }

    subtasks = await orchestrator.classify_task(task)

    yield {
        "agent": "orchestrator",
        "step": f"Planned {len(subtasks)} subtask(s)",
        "status": "done",
        "detail": str([s.get("agent") for s in subtasks]),
    }

    # Step 2: Execute subtasks (respecting dependencies)
    results: dict[str, dict] = {}
    completed: set[int] = set()

    for i, subtask in enumerate(subtasks):
        agent_name = subtask.get("agent", "chat")
        subtask_text = subtask.get("task", task)
        deps = subtask.get("depends_on", [])

        # Check dependencies
        for dep in deps:
            if dep not in completed:
                yield {
                    "agent": agent_name,
                    "step": f"Waiting for dependency {dep}",
                    "status": "running",
                }

        yield {
            "agent": agent_name,
            "step": f"Executing: {subtask_text[:80]}",
            "status": "running",
        }

        runner = AGENT_RUNNERS.get(agent_name)
        if runner:
            try:
                result = await runner(subtask_text)
                results[f"{agent_name}_{i}"] = result
                yield {
                    "agent": agent_name,
                    "step": "Completed",
                    "status": "done",
                    "detail": str(result)[:200],
                }
            except Exception as exc:
                logger.error("Agent %s failed: %s", agent_name, exc)
                yield {
                    "agent": agent_name,
                    "step": f"Error: {exc}",
                    "status": "error",
                    "detail": str(exc),
                }
        else:
            # Unknown agent — skip
            yield {
                "agent": agent_name,
                "step": f"Unknown agent type: {agent_name}",
                "status": "error",
            }

        completed.add(i)

    # Step 3: Synthesize results
    if results:
        yield {
            "agent": "orchestrator",
            "step": "Synthesizing final response",
            "status": "running",
        }

        final = await orchestrator.synthesize(task, results)

        yield {
            "agent": "orchestrator",
            "step": "Complete",
            "status": "done",
            "detail": final,
            "final_response": final,
        }
    else:
        yield {
            "agent": "orchestrator",
            "step": "No agent results to synthesize",
            "status": "done",
            "final_response": "No agents were able to complete the task.",
        }
