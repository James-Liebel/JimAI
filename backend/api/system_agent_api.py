"""API routes for the system agent."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents.system_agent.agent import SystemAgent
from agents.system_agent.safety import AgentMode
from agents.system_agent.tools import app_launcher, filesystem, process, screen

router = APIRouter(prefix="/api/system-agent", tags=["system-agent"])
_active_agents: dict[str, SystemAgent] = {}


class AgentTaskRequest(BaseModel):
    task: str
    session_id: str
    mode: AgentMode = AgentMode.SUPERVISED


class ConfirmationResponse(BaseModel):
    session_id: str
    approved: bool


class BrowseRequest(BaseModel):
    path: str = "~"


class SearchRequest(BaseModel):
    root: str = "~"
    pattern: str = "*"
    recursive: bool = True
    extensions: list[str] | None = None
    content: str | None = None


class ReadRequest(BaseModel):
    path: str
    max_chars: int = 50_000


class KillProcessRequest(BaseModel):
    pid: int


class ScreenshotRequest(BaseModel):
    monitor: int = 1
    return_base64: bool = True
    save_path: str | None = None


class OpenPathRequest(BaseModel):
    path: str


@router.post("/run")
async def run_agent_task(req: AgentTaskRequest) -> StreamingResponse:
    """Run a system-agent task and stream events."""
    agent = SystemAgent(mode=req.mode)
    _active_agents[req.session_id] = agent

    async def event_stream():
        try:
            async for event in agent.run(req.task):
                payload = {"type": event.type, "data": event.data}
                yield f"data: {json.dumps(payload)}\n\n"
        finally:
            _active_agents.pop(req.session_id, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/confirm")
async def confirm_step(resp: ConfirmationResponse) -> dict[str, Any]:
    """Approve or deny a pending confirmation."""
    agent = _active_agents.get(resp.session_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="No active system agent for that session")
    agent.confirm_step(resp.approved)
    return {"confirmed": resp.approved}


@router.get("/stats")
async def get_stats() -> dict[str, Any]:
    return process.get_system_stats()


@router.get("/processes")
async def get_processes(filter_name: str | None = None) -> dict[str, Any]:
    processes = process.list_processes(filter_name)
    return {"processes": [process.process_info_to_dict(item) for item in processes]}


@router.post("/processes/kill")
async def kill_process(req: KillProcessRequest) -> dict[str, Any]:
    return process.kill_process(req.pid)


@router.post("/browse")
async def browse_filesystem(req: BrowseRequest) -> dict[str, Any]:
    return filesystem.list_directory(req.path)


@router.post("/search")
async def search_filesystem(req: SearchRequest) -> dict[str, Any]:
    result = filesystem.search_files(
        root=req.root,
        pattern=req.pattern,
        recursive=req.recursive,
        include_extensions=req.extensions,
        content_contains=req.content,
    )
    return filesystem.search_result_to_dict(result)


@router.post("/read")
async def read_text_file(req: ReadRequest) -> dict[str, Any]:
    return filesystem.read_file(req.path, max_chars=req.max_chars)


@router.post("/screenshot")
async def take_screenshot(req: ScreenshotRequest) -> dict[str, Any]:
    return screen.take_screenshot(
        monitor=req.monitor,
        save_path=req.save_path,
        return_base64=req.return_base64,
    )


@router.post("/open-path")
async def open_path(req: OpenPathRequest) -> dict[str, Any]:
    return app_launcher.open_path(req.path)
