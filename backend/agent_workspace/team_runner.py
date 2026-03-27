"""Run multi-agent teams with streaming execution log."""

import asyncio
import json
from typing import AsyncGenerator

from agent_workspace.context import build_agent_context
from agent_workspace.models import Agent, Team
from agent_workspace.store import get_agent
from models import ollama_client


async def _generate_full(model: str, system: str, prompt: str) -> str:
    parts: list[str] = []
    async for chunk in ollama_client.generate(
        model=model,
        prompt=prompt,
        system=system,
        stream=True,
        temperature=0.5,
        num_ctx=16384,
    ):
        parts.append(chunk)
    return "".join(parts)


async def stream_team_run(team: Team, task: str) -> AsyncGenerator[str, None]:
    """Stream JSON lines: log events and text chunks per agent."""
    agents_ordered: list[Agent] = []
    for aid in team.agent_ids:
        a = get_agent(aid)
        if a:
            agents_ordered.append(a)

    if not agents_ordered:
        yield f"data: {json.dumps({'type': 'error', 'message': 'No agents in team'})}\n\n"
        return

    shared = team.shared_skills or []
    wf = team.workflow

    if wf == "parallel":

        async def run_one(agent: Agent) -> tuple[str, str]:
            sys_p = build_agent_context(agent, extra_shared_paths=shared)
            pr = f"Team task (execute your part; other agents work in parallel):\n\n{task}"
            text = await _generate_full(agent.model, sys_p, pr)
            return agent.slug, text

        yield f"data: {json.dumps({'type': 'log', 'message': f'Running {len(agents_ordered)} agents in parallel'})}\n\n"
        results = await asyncio.gather(*[run_one(a) for a in agents_ordered])
        combined = "\n\n---\n\n".join(f"## {slug}\n{txt}" for slug, txt in results)
        for slug, txt in results:
            yield f"data: {json.dumps({'type': 'agent_done', 'agent': slug, 'preview': txt[:500]})}\n\n"
        lead = agents_ordered[0]
        syn_sys = build_agent_context(lead, extra_shared_paths=shared)
        syn_prompt = (
            "Synthesize these parallel agent outputs into one coherent deliverable.\n\n" + combined
        )
        async for chunk in ollama_client.generate(
            model=lead.model,
            prompt=syn_prompt,
            system=syn_sys,
            stream=True,
            temperature=0.4,
            num_ctx=16384,
        ):
            yield f"data: {json.dumps({'type': 'chunk', 'phase': 'synthesis', 'text': chunk})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    if wf == "orchestrated":
        lead = agents_ordered[0]
        others = agents_ordered[1:]
        roster = ", ".join(f"{a.name} ({a.role})" for a in others)
        sys_p = build_agent_context(lead, extra_shared_paths=shared)
        prompt = (
            f"You orchestrate: {roster}\n\n"
            f"Task: {task}\n\n"
            "Produce a plan delegating subtasks, then simulate each specialist's contribution "
            "(clearly labeled sections), then a final integrated answer."
        )
        yield f"data: {json.dumps({'type': 'log', 'message': f'Orchestrator: {lead.slug}'})}\n\n"
        async for chunk in ollama_client.generate(
            model=lead.model,
            prompt=prompt,
            system=sys_p,
            stream=True,
            temperature=0.5,
            num_ctx=32768,
        ):
            yield f"data: {json.dumps({'type': 'chunk', 'agent': lead.slug, 'text': chunk})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    # sequential (default)
    prior = ""
    for i, agent in enumerate(agents_ordered):
        yield f"data: {json.dumps({'type': 'log', 'message': f'Starting {agent.name} ({agent.slug})'})}\n\n"
        sys_p = build_agent_context(agent, extra_shared_paths=shared)
        if i == 0:
            prompt = f"Task:\n{task}"
        else:
            prompt = (
                f"Original team task:\n{task}\n\n"
                f"Output from previous agent:\n{prior}\n\n"
                "Continue the workflow: build on the above and produce your part."
            )
        buf: list[str] = []
        async for chunk in ollama_client.generate(
            model=agent.model,
            prompt=prompt,
            system=sys_p,
            stream=True,
            temperature=0.5,
            num_ctx=16384,
        ):
            buf.append(chunk)
            yield f"data: {json.dumps({'type': 'chunk', 'agent': agent.slug, 'text': chunk})}\n\n"
        prior = "".join(buf)
        yield f"data: {json.dumps({'type': 'agent_done', 'agent': agent.slug})}\n\n"

    yield f"data: {json.dumps({'type': 'done', 'final': prior})}\n\n"
