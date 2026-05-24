"""Per-user credential vault for Atlas autofill — encrypted at rest, bound to this
machine.

Storage: data/memory/credentials.enc — a JSON blob encrypted via local_cipher,
which uses Windows DPAPI (current-user scope) when available. That binds the data
to this Windows account + machine: copying the file elsewhere yields ciphertext
that cannot be decrypted, and nothing is exposed over the network. Falls back to a
local Fernet key, then to plaintext with a loud warning, on platforms without DPAPI.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import threading
from typing import Any
from urllib.parse import urlparse

from config.settings import PROJECT_ROOT

from . import local_cipher as cipher

logger = logging.getLogger(__name__)

_VAULT_DIR = PROJECT_ROOT / "data" / "memory"
_VAULT_FILE = _VAULT_DIR / "credentials.enc"
_LOCK = threading.RLock()


def _load_all() -> dict[str, Any]:
    if not _VAULT_FILE.exists():
        return {"users": {}}
    try:
        text = _VAULT_FILE.read_text(encoding="utf-8")
        if not text.strip():
            return {"users": {}}
        data = json.loads(cipher.decrypt_str(text))
        if not isinstance(data, dict):
            return {"users": {}}
        if "users" not in data or not isinstance(data["users"], dict):
            data["users"] = {}
        return data
    except Exception:
        logger.warning("credentials_vault: existing blob unreadable — starting fresh")
        return {"users": {}}


def _save_all(data: dict[str, Any]) -> None:
    _VAULT_DIR.mkdir(parents=True, exist_ok=True)
    _VAULT_FILE.write_text(
        cipher.encrypt_str(json.dumps(data, ensure_ascii=False)), encoding="utf-8"
    )
    try:
        os.chmod(_VAULT_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


def canonical_origin(url_or_origin: str) -> str:
    """Reduce a URL to scheme://host[:port] so 'gmail.com/inbox' and 'gmail.com/' share creds."""
    raw = (url_or_origin or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    try:
        u = urlparse(raw)
    except Exception:
        return ""
    if not u.hostname:
        return ""
    scheme = (u.scheme or "https").lower()
    host = u.hostname.lower()
    port = f":{u.port}" if u.port and not (
        (scheme == "https" and u.port == 443) or (scheme == "http" and u.port == 80)
    ) else ""
    return f"{scheme}://{host}{port}"


def get_credential(user_id: str, origin: str) -> dict | None:
    origin = canonical_origin(origin)
    if not origin:
        return None
    with _LOCK:
        data = _load_all()
    entries = data.get("users", {}).get(user_id, {})
    rec = entries.get(origin)
    if not isinstance(rec, dict):
        return None
    return {"origin": origin, "username": rec.get("username", ""), "password": rec.get("password", "")}


def save_credential(user_id: str, origin: str, username: str, password: str) -> dict:
    origin = canonical_origin(origin)
    if not origin:
        raise ValueError("invalid origin")
    with _LOCK:
        data = _load_all()
        users = data.setdefault("users", {})
        user_entries = users.setdefault(user_id, {})
        user_entries[origin] = {"username": username, "password": password}
        _save_all(data)
    return {"origin": origin, "username": username, "saved": True}


def delete_credential(user_id: str, origin: str) -> bool:
    origin = canonical_origin(origin)
    if not origin:
        return False
    with _LOCK:
        data = _load_all()
        user_entries = data.get("users", {}).get(user_id, {})
        if origin not in user_entries:
            return False
        del user_entries[origin]
        _save_all(data)
    return True


def list_origins(user_id: str) -> list[dict]:
    """Return [{origin, username}] — never the password."""
    with _LOCK:
        data = _load_all()
    user_entries = data.get("users", {}).get(user_id, {})
    out: list[dict] = []
    for origin, rec in user_entries.items():
        if isinstance(rec, dict):
            out.append({"origin": origin, "username": rec.get("username", "")})
    out.sort(key=lambda r: r["origin"])
    return out
