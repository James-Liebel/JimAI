"""Workspace routes for IDE-style repository editing."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent_space.paths import PROJECT_ROOT

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


class CreateDirectoryRequest(BaseModel):
    path: str = Field(min_length=1, max_length=600)


def _resolve_repo_path(path: str) -> tuple[str, Path]:
    cleaned = str(path or "").replace("\\", "/").strip() or "."
    target = (PROJECT_ROOT / cleaned).resolve() if not Path(cleaned).is_absolute() else Path(cleaned).resolve()
    project_root = PROJECT_ROOT.resolve()
    try:
        target.relative_to(project_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Path is outside repository.") from exc
    rel = target.relative_to(project_root).as_posix() if target != project_root else "."
    return rel, target


@router.post("/directory")
async def create_directory(req: CreateDirectoryRequest) -> dict[str, str]:
    rel, abs_path = _resolve_repo_path(req.path)
    abs_path.mkdir(parents=True, exist_ok=True)
    return {"path": rel}
