"""Agent APIs — legacy graph run/status + workspace agents/skills/chat."""

import asyncio
import json
import logging
import re
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_workspace.generator import generate_skill_markdown
from agent_workspace.models import Agent
from agent_workspace.runner import run_agent_task, stream_agent_chat
from agent_workspace.skills import delete_skill, list_skills_for_agent, read_skill, write_skill
from agent_workspace.store import (
    create_agent,
    delete_agent,
    get_agent,
    load_agents,
    update_agent,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["agents"])

_status_queue: asyncio.Queue | None = None


def get_status_queue() -> asyncio.Queue:
    global _status_queue
    if _status_queue is None:
        _status_queue = asyncio.Queue()
    return _status_queue


async def _broadcast_status(agent: str, step: str, status: str, detail: str = "") -> None:
    q = get_status_queue()
    await q.put({"agent": agent, "step": step, "status": status, "detail": detail})


# ── Legacy: multi-agent graph ──────────────────────────────────────────


class AgentRunRequest(BaseModel):
    task: str
    session_id: str = "default"


async def _run_agent_task(task: str, session_id: str) -> AsyncGenerator[str, None]:
    try:
        from agents.graph import run_graph

        async for update in run_graph(task, session_id):
            await _broadcast_status(
                agent=update.get("agent", "orchestrator"),
                step=update.get("step", ""),
                status=update.get("status", "running"),
                detail=update.get("detail", ""),
            )
            yield f"data: {json.dumps(update)}\n\n"
    except Exception as exc:
        logger.error("Agent run failed: %s", exc)
        error = {"agent": "system", "step": "error", "status": "error", "detail": str(exc)}
        yield f"data: {json.dumps(error)}\n\n"


@router.post("/run")
async def run_agents(req: AgentRunRequest) -> StreamingResponse:
    """Run the agent graph on a complex task. Streams progress as SSE."""
    return StreamingResponse(
        _run_agent_task(req.task, req.session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/status")
async def agent_status() -> StreamingResponse:
    async def _stream() -> AsyncGenerator[str, None]:
        q = get_status_queue()
        while True:
            try:
                update = await asyncio.wait_for(q.get(), timeout=30.0)
                yield f"data: {json.dumps(update)}\n\n"
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'keepalive': True})}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Workspace: list Ollama models ─────────────────────────────────────


@router.get("/models")
async def list_ollama_models():
    from models import ollama_client

    try:
        names = await ollama_client.list_models()
        return {"models": names}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


# ── Workspace: CRUD agents ────────────────────────────────────────────


class AgentCreateBody(BaseModel):
    name: str
    role: str
    slug: str | None = None
    avatar: str = "🤖"
    model: str = "qwen3:8b"
    system_prompt: str = ""


class AgentUpdateBody(BaseModel):
    name: str | None = None
    role: str | None = None
    slug: str | None = None
    avatar: str | None = None
    model: str | None = None
    system_prompt: str | None = None
    memory_enabled: bool | None = None
    tools: list[str] | None = None
    skills: list[str] | None = None
    status: str | None = None


@router.get("")
async def workspace_list_agents():
    return {"agents": [a.model_dump() for a in load_agents()]}


@router.post("")
async def workspace_create_agent(body: AgentCreateBody):
    agent = create_agent(
        name=body.name,
        role=body.role,
        slug=body.slug,
        avatar=body.avatar,
        model=body.model,
        system_prompt=body.system_prompt,
    )
    return agent.model_dump()


@router.get("/{agent_id}")
async def workspace_get_agent(agent_id: str):
    if agent_id in ("run", "status", "models"):
        raise HTTPException(status_code=404, detail="Not found")
    a = get_agent(agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="Agent not found")
    skills = list_skills_for_agent(a)
    data = a.model_dump()
    data["skill_files"] = [s.__dict__ for s in skills]
    return data


@router.put("/{agent_id}")
async def workspace_put_agent(agent_id: str, body: AgentUpdateBody):
    if agent_id in ("run", "status", "models"):
        raise HTTPException(status_code=404, detail="Not found")
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    a = update_agent(agent_id, **fields)
    if not a:
        raise HTTPException(status_code=404, detail="Agent not found")
    return a.model_dump()


@router.delete("/{agent_id}")
async def workspace_delete_agent(agent_id: str):
    if agent_id in ("run", "status", "models"):
        raise HTTPException(status_code=404, detail="Not found")
    if not delete_agent(agent_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"deleted": True}


# ── Skills ─────────────────────────────────────────────────────────────


class SkillGenerateBody(BaseModel):
    skill_name: str
    skill_description: str = ""
    example_task: str | None = None


class SkillSaveBody(BaseModel):
    content: str
    skill_slug: str | None = None


def _slug_from_name(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower().strip()).strip("-")
    return s or "skill"


@router.get("/{agent_id}/skills")
async def list_agent_skills(agent_id: str):
    a = get_agent(agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="Agent not found")
    skills = list_skills_for_agent(a)
    return {"skills": [s.__dict__ for s in skills]}


@router.post("/{agent_id}/skills/generate")
async def generate_agent_skill(agent_id: str, body: SkillGenerateBody):
    a = get_agent(agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="Agent not found")
    markdown = await generate_skill_markdown(
        agent_name=a.name,
        agent_role=a.role,
        skill_name=body.skill_name,
        skill_description=body.skill_description,
        example_task=body.example_task,
        model=a.model,
    )
    suggested_slug = _slug_from_name(body.skill_name)
    return {"markdown": markdown, "suggested_slug": suggested_slug}


@router.put("/{agent_id}/skills/{skill_slug}")
async def save_agent_skill(agent_id: str, skill_slug: str, body: SkillSaveBody):
    a = get_agent(agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="Agent not found")
    slug = body.skill_slug or skill_slug
    path = write_skill(a.slug, slug, body.content)
    return {"saved": True, "path": str(path)}


@router.delete("/{agent_id}/skills/{skill_slug}")
async def remove_agent_skill(agent_id: str, skill_slug: str):
    a = get_agent(agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not delete_skill(a.slug, skill_slug):
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"deleted": True}


@router.get("/{agent_id}/skills/{skill_slug}/raw")
async def get_skill_raw(agent_id: str, skill_slug: str):
    a = get_agent(agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        return {"content": read_skill(a.slug, skill_slug)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Skill not found") from None


# ── Chat & task ─────────────────────────────────────────────────────────


class AgentChatBody(BaseModel):
    message: str
    history: list[dict] = Field(default_factory=list)


@router.post("/{agent_id}/chat")
async def agent_chat(agent_id: str, body: AgentChatBody):
    a = get_agent(agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="Agent not found")

    async def _stream() -> AsyncGenerator[str, None]:
        async for line in stream_agent_chat(a, body.message, body.history):
            yield line

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class AgentTaskBody(BaseModel):
    task: str


@router.post("/{agent_id}/run-task")
async def agent_run_task_ep(agent_id: str, body: AgentTaskBody):
    a = get_agent(agent_id)
    if not a:
        raise HTTPException(status_code=404, detail="Agent not found")

    async def _stream() -> AsyncGenerator[str, None]:
        async for line in run_agent_task(a, body.task):
            yield line

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
