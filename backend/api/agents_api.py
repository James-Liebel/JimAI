"""Agent orchestration API — runs multi-agent tasks and streams status."""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["agents"])

# Shared queue for broadcasting agent status to connected clients
_status_queue: asyncio.Queue | None = None


def get_status_queue() -> asyncio.Queue:
    global _status_queue
    if _status_queue is None:
        _status_queue = asyncio.Queue()
    return _status_queue


class AgentRunRequest(BaseModel):
    task: str
    session_id: str = "default"


async def _broadcast_status(agent: str, step: str, status: str, detail: str = "") -> None:
    """Push a status update to all listening clients."""
    q = get_status_queue()
    await q.put({
        "agent": agent,
        "step": step,
        "status": status,
        "detail": detail,
    })


async def _run_agent_task(task: str, session_id: str) -> AsyncGenerator[str, None]:
    """Execute the agent graph and stream status updates as SSE."""
    try:
        from agents.graph import run_graph

        async for update in run_graph(task, session_id):
            # Broadcast to the status SSE stream
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
    """SSE stream of agent activity — used by the AgentStatus UI component."""

    async def _stream() -> AsyncGenerator[str, None]:
        q = get_status_queue()
        while True:
            try:
                update = await asyncio.wait_for(q.get(), timeout=30.0)
                yield f"data: {json.dumps(update)}\n\n"
            except asyncio.TimeoutError:
                # Send keepalive
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
