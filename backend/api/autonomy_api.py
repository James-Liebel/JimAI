"""Autonomy primitives API.

Exposes episodic memory, skill library, reflections, replan evaluator, and
the heartbeat scheduler as a small REST surface. Read-mostly; mutations are
gated by the existing CSRF + API-key middleware.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from agent_space.autonomy import runtime as autonomy_runtime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autonomy", tags=["autonomy"])


# --------------------------------------------------------------------- memory


@router.get("/memory/stats")
async def memory_stats() -> dict[str, Any]:
    return autonomy_runtime.get_episodic_memory().stats()


@router.get("/memory/recent")
async def memory_recent(limit: int = 50) -> dict[str, Any]:
    rows = autonomy_runtime.get_episodic_memory().list_recent(limit=limit)
    return {"items": [r.to_dict() for r in rows]}


@router.get("/memory/run/{run_id}")
async def memory_for_run(run_id: str, limit: int = 200) -> dict[str, Any]:
    rows = autonomy_runtime.get_episodic_memory().list_by_run(run_id, limit=limit)
    return {"run_id": run_id, "items": [r.to_dict() for r in rows]}


@router.post("/memory/search")
async def memory_search(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    limit = int(payload.get("limit") or 5)
    min_score = float(payload.get("min_score") or 0.55)
    hits = await autonomy_runtime.get_episodic_memory().search(
        query, limit=limit, min_score=min_score
    )
    return {
        "query": query,
        "results": [
            {**rec.to_dict(), "score": round(score, 4)}
            for rec, score in hits
        ],
    }


@router.post("/memory/consolidate")
async def memory_consolidate(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    max_per_run = int(payload.get("max_per_run") or 3)
    consolidated = await autonomy_runtime.get_episodic_memory().consolidate(
        max_per_run=max_per_run
    )
    return {"consolidated": consolidated}


# ---------------------------------------------------------------- skill library


@router.get("/skills/stats")
async def skills_stats() -> dict[str, Any]:
    return autonomy_runtime.get_skill_library().stats()


@router.get("/skills")
async def skills_list(limit: int = 200) -> dict[str, Any]:
    rows = autonomy_runtime.get_skill_library().list_all(limit=limit)
    return {"items": [r.to_dict() for r in rows]}


@router.post("/skills/retrieve")
async def skills_retrieve(payload: dict[str, Any]) -> dict[str, Any]:
    objective = str(payload.get("objective") or "").strip()
    if not objective:
        raise HTTPException(status_code=400, detail="objective is required")
    limit = int(payload.get("limit") or 5)
    artifact_type = payload.get("artifact_type")
    hits = await autonomy_runtime.get_skill_library().retrieve(
        objective,
        limit=limit,
        artifact_type=str(artifact_type) if artifact_type else None,
    )
    return {
        "objective": objective,
        "results": [
            {**entry.to_dict(), "score": round(score, 4)}
            for entry, score in hits
        ],
    }


@router.post("/skills/capture")
async def skills_capture(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    artifact = str(payload.get("artifact") or "").strip()
    if not artifact:
        raise HTTPException(status_code=400, detail="artifact is required")
    entry = await autonomy_runtime.get_skill_library().capture(
        name=name,
        description=str(payload.get("description") or ""),
        objective=str(payload.get("objective") or ""),
        artifact=artifact,
        artifact_type=str(payload.get("artifact_type") or "code"),
        tags=list(payload.get("tags") or []),
        verifier_score=float(payload.get("verifier_score") or 1.0),
        metadata=dict(payload.get("metadata") or {}),
    )
    return entry.to_dict()


@router.delete("/skills/{entry_id}")
async def skills_delete(entry_id: str) -> dict[str, Any]:
    ok = await autonomy_runtime.get_skill_library().delete(entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="skill not found")
    return {"ok": True, "id": entry_id}


# ------------------------------------------------------------------ reflection


@router.get("/reflections/stats")
async def reflections_stats() -> dict[str, Any]:
    return autonomy_runtime.get_reflection_engine().stats()


@router.post("/reflections/lookup")
async def reflections_lookup(payload: dict[str, Any]) -> dict[str, Any]:
    objective = str(payload.get("objective") or "").strip()
    if not objective:
        raise HTTPException(status_code=400, detail="objective is required")
    limit = int(payload.get("limit") or 4)
    rows = autonomy_runtime.get_reflection_engine().lessons_for(objective, limit=limit)
    return {
        "objective": objective,
        "lessons": [r.to_dict() for r in rows],
    }


# --------------------------------------------------------------------- heartbeat


@router.get("/heartbeat/status")
async def heartbeat_status() -> dict[str, Any]:
    sched = autonomy_runtime.get_heartbeat_scheduler()
    if sched is None:
        return {"running": False, "bound": False, "job_count": 0}
    status = sched.status()
    status["bound"] = True
    return status


@router.get("/heartbeat/jobs")
async def heartbeat_jobs() -> dict[str, Any]:
    sched = autonomy_runtime.get_heartbeat_scheduler()
    if sched is None:
        return {"items": []}
    rows = sched.list_jobs()
    return {"items": [r.to_dict() for r in rows]}


@router.post("/heartbeat/start")
async def heartbeat_start() -> dict[str, Any]:
    sched = autonomy_runtime.get_heartbeat_scheduler()
    if sched is None:
        raise HTTPException(status_code=503, detail="heartbeat scheduler not bound")
    return await sched.start()


@router.post("/heartbeat/stop")
async def heartbeat_stop() -> dict[str, Any]:
    sched = autonomy_runtime.get_heartbeat_scheduler()
    if sched is None:
        raise HTTPException(status_code=503, detail="heartbeat scheduler not bound")
    return await sched.stop()


@router.post("/heartbeat/tick")
async def heartbeat_tick() -> dict[str, Any]:
    sched = autonomy_runtime.get_heartbeat_scheduler()
    if sched is None:
        raise HTTPException(status_code=503, detail="heartbeat scheduler not bound")
    return await sched.tick()


@router.post("/heartbeat/jobs")
async def heartbeat_add_job(payload: dict[str, Any]) -> dict[str, Any]:
    sched = autonomy_runtime.get_heartbeat_scheduler()
    if sched is None:
        raise HTTPException(status_code=503, detail="heartbeat scheduler not bound")
    name = str(payload.get("name") or "").strip()
    objective = str(payload.get("objective") or "").strip()
    if not name or not objective:
        raise HTTPException(status_code=400, detail="name and objective are required")
    job = await sched.add_job(
        name=name,
        objective=objective,
        interval_seconds=float(payload.get("interval_seconds") or 900.0),
        one_shot=bool(payload.get("one_shot") or False),
        first_fire_in_seconds=(
            float(payload["first_fire_in_seconds"])
            if payload.get("first_fire_in_seconds") is not None
            else None
        ),
        payload=dict(payload.get("payload") or {}),
        metadata=dict(payload.get("metadata") or {}),
        enabled=bool(payload.get("enabled", True)),
    )
    return job.to_dict()


@router.patch("/heartbeat/jobs/{job_id}")
async def heartbeat_update_job(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    sched = autonomy_runtime.get_heartbeat_scheduler()
    if sched is None:
        raise HTTPException(status_code=503, detail="heartbeat scheduler not bound")
    try:
        job = await sched.update_job(job_id, payload or {})
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return job.to_dict()


@router.delete("/heartbeat/jobs/{job_id}")
async def heartbeat_delete_job(job_id: str) -> dict[str, Any]:
    sched = autonomy_runtime.get_heartbeat_scheduler()
    if sched is None:
        raise HTTPException(status_code=503, detail="heartbeat scheduler not bound")
    ok = await sched.delete_job(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "id": job_id}
