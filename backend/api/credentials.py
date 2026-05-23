"""HTTP surface for the per-user credential vault used by Atlas autofill.

All endpoints scope to the active user (or one explicitly named in the
request) via api.users.resolve_user_id, matching the rest of the app's
identity model.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from api.users import resolve_user_id
from memory import credentials_vault as vault

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


def _active_uid() -> str:
    """Resolve the credential owner.

    Security: always the active local profile. We deliberately ignore any
    client-supplied user_id so a caller cannot read another user's stored
    passwords by guessing their id (IDOR) — there is no per-user auth boundary.
    """
    return resolve_user_id(None)


class SaveCredentialRequest(BaseModel):
    origin: str
    username: str
    password: str
    user_id: str | None = None


class DeleteCredentialRequest(BaseModel):
    origin: str
    user_id: str | None = None


@router.get("")
async def get_for_origin(origin: str, user_id: str | None = None) -> dict:
    """Return {origin, username, password} for the active user's record, or {found: False}."""
    uid = _active_uid()
    rec = vault.get_credential(uid, origin)
    if rec is None:
        return {"found": False, "origin": vault.canonical_origin(origin)}
    return {"found": True, **rec}


@router.put("")
async def save(req: SaveCredentialRequest) -> dict:
    uid = _active_uid()
    try:
        return vault.save_credential(uid, req.origin, req.username, req.password)
    except ValueError as exc:
        return {"saved": False, "error": str(exc)}


@router.delete("")
async def remove(origin: str, user_id: str | None = None) -> dict:
    uid = _active_uid()
    return {"deleted": vault.delete_credential(uid, origin)}


@router.get("/list")
async def list_all(user_id: str | None = None) -> dict:
    uid = _active_uid()
    return {"user_id": uid, "entries": vault.list_origins(uid)}
