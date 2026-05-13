"""Local user-profile endpoints (no real auth — this is a local app).

Each request to /api/chat can include a user_id; without one we fall back to
the active profile, which the frontend selects via /api/users/active. This is
the identity that scopes cross-chat memory and lets the assistant learn about
distinct users sharing the same machine.
"""

from __future__ import annotations

import re
import time

from fastapi import APIRouter
from pydantic import BaseModel

from memory import db

router = APIRouter(prefix="/api/users", tags=["users"])

_ACTIVE_SLOT = "_active_profile"
_SYSTEM_USER = "__system__"
_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")


class UserCreateRequest(BaseModel):
    id: str
    label: str = ""


class ActiveUserRequest(BaseModel):
    id: str


def _list_users() -> list[dict]:
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT id, label, created_at FROM users WHERE id != ? ORDER BY created_at ASC",
        (_SYSTEM_USER,),
    ).fetchall()
    return [dict(r) for r in rows]


def _get_active() -> str:
    rec = db.read_user_slot(_SYSTEM_USER, _ACTIVE_SLOT)
    if rec and isinstance(rec.get("data"), dict):
        val = str(rec["data"].get("id") or "").strip()
        if val:
            return val
    return db.DEFAULT_USER_ID


def resolve_user_id(requested: str | None) -> str:
    """Public helper used by other routers to canonicalize an incoming user_id."""
    raw = (requested or "").strip()
    if raw and _ID_RE.match(raw):
        db.ensure_user(raw)
        return raw
    return _get_active()


@router.get("")
async def list_users() -> dict:
    return {"users": _list_users(), "active": _get_active()}


@router.post("")
async def create_user(req: UserCreateRequest) -> dict:
    uid = req.id.strip()
    if not _ID_RE.match(uid):
        return {"error": "invalid_id", "message": "Use 1-64 chars: letters, digits, '_', '.', '-'"}
    db.ensure_user(uid, label=req.label.strip())
    return {"id": uid, "label": req.label.strip(), "created_at": time.time()}


@router.delete("/{user_id}")
async def delete_user(user_id: str) -> dict:
    if user_id in (db.DEFAULT_USER_ID, _SYSTEM_USER):
        return {"deleted": False, "error": "protected"}
    if not _ID_RE.match(user_id):
        return {"deleted": False, "error": "invalid_id"}
    conn = db.get_conn()
    # Cascades through chats → messages via FK ON DELETE CASCADE.
    conn.execute("DELETE FROM chats WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM user_memory WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    if _get_active() == user_id:
        db.write_user_slot(_SYSTEM_USER, _ACTIVE_SLOT, {"id": db.DEFAULT_USER_ID})
    return {"deleted": True}


@router.get("/active")
async def get_active() -> dict:
    return {"id": _get_active()}


@router.post("/active")
async def set_active(req: ActiveUserRequest) -> dict:
    uid = req.id.strip()
    if not _ID_RE.match(uid):
        return {"error": "invalid_id"}
    db.ensure_user(uid)
    db.write_user_slot(_SYSTEM_USER, _ACTIVE_SLOT, {"id": uid})
    return {"id": uid}
