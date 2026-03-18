from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import json
from pathlib import Path

router = APIRouter(prefix="/api/agents/builder")

AGENTS_DIR = Path("data/agents")
AGENTS_DIR.mkdir(parents=True, exist_ok=True)

class SubagentConfig(BaseModel):
    name: str
    role: str
    model: str
    tools: list[str]
    prompt_template: str

class AgentConfig(BaseModel):
    id: str
    name: str
    description: str
    trigger: str
    model: str
    system_prompt: str
    subagents: list[SubagentConfig]
    tools: list[str]
    max_iterations: int = 5

@router.get("/list")
async def list_agents():
    agents = []
    for p in AGENTS_DIR.glob("*.json"):
        with open(p, "r", encoding="utf-8") as f:
            agents.append(json.load(f))
    return {"agents": agents}

@router.post("/save")
async def save_agent(config: AgentConfig):
    file_path = AGENTS_DIR / f"{config.id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(config.dict(), f, indent=2)
    return {"status": "success", "id": config.id}

@router.delete("/{agent_id}")
async def delete_agent(agent_id: str):
    file_path = AGENTS_DIR / f"{agent_id}.json"
    if file_path.exists():
        file_path.unlink()
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Agent not found")

@router.post("/run")
async def run_custom_agent(agent_id: str, task: str, session_id: str):
    # This would stream SSE like the main orchestrator, dynamically using the graph
    return {"status": "started", "session_id": session_id}
