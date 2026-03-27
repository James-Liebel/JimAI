"""Pydantic models for workspace agents and teams."""

from typing import Literal

from pydantic import BaseModel, Field


class Agent(BaseModel):
    id: str
    slug: str
    name: str
    role: str
    avatar: str = "🤖"
    model: str = "qwen3:8b"
    system_prompt: str = ""
    skills: list[str] = Field(default_factory=list)
    memory_enabled: bool = True
    tools: list[str] = Field(default_factory=list)
    team_ids: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    status: Literal["idle", "running", "error"] = "idle"


class Team(BaseModel):
    id: str
    name: str
    description: str = ""
    agent_ids: list[str] = Field(default_factory=list)
    workflow: Literal["sequential", "parallel", "orchestrated"] = "orchestrated"
    shared_skills: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class AgentsFile(BaseModel):
    agents: list[Agent] = Field(default_factory=list)


class TeamsFile(BaseModel):
    teams: list[Team] = Field(default_factory=list)
