"""JSON persistence for agents and teams."""

import json
import time
import uuid
from pathlib import Path

from agent_workspace.models import Agent, AgentsFile, Team, TeamsFile
from agent_workspace.paths import AGENTS_FILE, DATA_DIR, TEAMS_FILE
from agent_workspace.defaults import default_agents_list


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(name: str) -> str:
    s = "".join(c if c.isalnum() or c in "-_" else "-" for c in name.lower().strip())
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-") or "agent"


def load_agents() -> list[Agent]:
    _ensure_dir()
    if not AGENTS_FILE.exists():
        agents = default_agents_list()
        save_agents(agents)
        return agents
    raw = json.loads(AGENTS_FILE.read_text(encoding="utf-8"))
    data = AgentsFile.model_validate(raw)
    return data.agents


def save_agents(agents: list[Agent]) -> None:
    _ensure_dir()
    AGENTS_FILE.write_text(
        AgentsFile(agents=agents).model_dump_json(indent=2),
        encoding="utf-8",
    )


def get_agent(agent_id: str) -> Agent | None:
    for a in load_agents():
        if a.id == agent_id:
            return a
    return None


def get_agent_by_slug(slug: str) -> Agent | None:
    for a in load_agents():
        if a.slug == slug:
            return a
    return None


def create_agent(
    name: str,
    role: str,
    slug: str | None = None,
    avatar: str = "🤖",
    model: str = "qwen3:8b",
    system_prompt: str = "",
) -> Agent:
    agents = load_agents()
    sid = _slugify(slug or name)
    if any(a.slug == sid for a in agents):
        sid = f"{sid}-{uuid.uuid4().hex[:6]}"
    agent = Agent(
        id=str(uuid.uuid4()),
        slug=sid,
        name=name,
        role=role,
        avatar=avatar,
        model=model,
        system_prompt=system_prompt or f"You are {name}. {role}.",
        skills=[],
        memory_enabled=True,
        tools=[],
        team_ids=[],
        created_at=_now_iso(),
        updated_at=_now_iso(),
    )
    agents.append(agent)
    save_agents(agents)
    return agent


def update_agent(agent_id: str, **fields) -> Agent | None:
    agents = load_agents()
    for i, a in enumerate(agents):
        if a.id == agent_id:
            data = a.model_dump()
            for k, v in fields.items():
                if k in data and v is not None:
                    data[k] = v
            data["updated_at"] = _now_iso()
            agents[i] = Agent.model_validate(data)
            save_agents(agents)
            return agents[i]
    return None


def delete_agent(agent_id: str) -> bool:
    agents = load_agents()
    new_list = [a for a in agents if a.id != agent_id]
    if len(new_list) == len(agents):
        return False
    save_agents(new_list)
    teams = load_teams()
    changed = False
    for t in teams:
        if agent_id in t.agent_ids:
            t.agent_ids = [x for x in t.agent_ids if x != agent_id]
            changed = True
    if changed:
        save_teams(teams)
    return True


def load_teams() -> list[Team]:
    _ensure_dir()
    if not TEAMS_FILE.exists():
        save_teams([])
        return []
    raw = json.loads(TEAMS_FILE.read_text(encoding="utf-8"))
    return TeamsFile.model_validate(raw).teams


def save_teams(teams: list[Team]) -> None:
    _ensure_dir()
    TEAMS_FILE.write_text(
        TeamsFile(teams=teams).model_dump_json(indent=2),
        encoding="utf-8",
    )


def get_team(team_id: str) -> Team | None:
    for t in load_teams():
        if t.id == team_id:
            return t
    return None


def create_team(
    name: str,
    description: str = "",
    agent_ids: list[str] | None = None,
    workflow: str = "orchestrated",
    shared_skills: list[str] | None = None,
) -> Team:
    teams = load_teams()
    team = Team(
        id=str(uuid.uuid4()),
        name=name,
        description=description,
        agent_ids=agent_ids or [],
        workflow=workflow,  # type: ignore[arg-type]
        shared_skills=shared_skills or [],
        created_at=_now_iso(),
        updated_at=_now_iso(),
    )
    teams.append(team)
    save_teams(teams)
    _sync_agent_team_ids(teams)
    return team


def update_team(team_id: str, **fields) -> Team | None:
    teams = load_teams()
    for i, t in enumerate(teams):
        if t.id == team_id:
            data = t.model_dump()
            for k, v in fields.items():
                if k in data and v is not None:
                    data[k] = v
            data["updated_at"] = _now_iso()
            teams[i] = Team.model_validate(data)
            save_teams(teams)
            _sync_agent_team_ids(teams)
            return teams[i]
    return None


def delete_team(team_id: str) -> bool:
    teams = load_teams()
    new_list = [t for t in teams if t.id != team_id]
    if len(new_list) == len(teams):
        return False
    save_teams(new_list)
    _sync_agent_team_ids(new_list)
    return True


def _sync_agent_team_ids(teams: list[Team]) -> None:
    agents = load_agents()
    team_map: dict[str, set[str]] = {}
    for t in teams:
        for aid in t.agent_ids:
            team_map.setdefault(aid, set()).add(t.id)
    changed = False
    for i, a in enumerate(agents):
        new_ids = sorted(team_map.get(a.id, set()))
        if list(a.team_ids) != new_ids:
            agents[i] = a.model_copy(update={"team_ids": new_ids, "updated_at": _now_iso()})
            changed = True
    if changed:
        save_agents(agents)
