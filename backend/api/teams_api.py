"""Teams API for multi-agent workspace."""

import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_workspace.store import (
    create_team,
    delete_team,
    get_team,
    load_teams,
    update_team,
)
from agent_workspace.team_runner import stream_team_run

router = APIRouter(prefix="/api/teams", tags=["teams"])


class TeamCreateBody(BaseModel):
    name: str
    description: str = ""
    agent_ids: list[str] = Field(default_factory=list)
    workflow: str = "orchestrated"
    shared_skills: list[str] = Field(default_factory=list)


class TeamUpdateBody(BaseModel):
    name: str | None = None
    description: str | None = None
    agent_ids: list[str] | None = None
    workflow: str | None = None
    shared_skills: list[str] | None = None


@router.get("")
async def list_teams():
    return {"teams": [t.model_dump() for t in load_teams()]}


@router.post("")
async def create_team_ep(body: TeamCreateBody):
    team = create_team(
        name=body.name,
        description=body.description,
        agent_ids=body.agent_ids,
        workflow=body.workflow,
        shared_skills=body.shared_skills,
    )
    return team.model_dump()


@router.get("/{team_id}")
async def get_team_ep(team_id: str):
    t = get_team(team_id)
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")
    return t.model_dump()


@router.put("/{team_id}")
async def put_team(team_id: str, body: TeamUpdateBody):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    t = update_team(team_id, **fields)
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")
    return t.model_dump()


@router.delete("/{team_id}")
async def del_team(team_id: str):
    if not delete_team(team_id):
        raise HTTPException(status_code=404, detail="Team not found")
    return {"deleted": True}


class TeamRunBody(BaseModel):
    task: str


@router.post("/{team_id}/run")
async def run_team(team_id: str, body: TeamRunBody):
    t = get_team(team_id)
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")

    async def _stream() -> AsyncGenerator[str, None]:
        async for line in stream_team_run(t, body.task):
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
