"""Encrypted per-user credential vault for Atlas autofill.

Storage: data/memory/credentials.enc — a single JSON blob encrypted with
Fernet (AES-128-CBC + HMAC). Key lives at data/memory/.vault.key with 0600
permissions; generated lazily on first use.

This protects credentials at rest from casual disk inspection. It is *not*
defence against an attacker with code execution as the user — for that you
want the OS keychain (DPAPI/Keychain/libsecret), which is a follow-up.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken

from config.settings import PROJECT_ROOT

logger = logging.getLogger(__name__)

_VAULT_DIR = PROJECT_ROOT / "data" / "memory"
_VAULT_FILE = _VAULT_DIR / "credentials.enc"
_KEY_FILE = _VAULT_DIR / ".vault.key"
_LOCK = threading.RLock()


def _load_key() -> bytes:
    _VAULT_DIR.mkdir(parents=True, exist_ok=True)
    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes()
    key = Fernet.generate_key()
    _KEY_FILE.write_bytes(key)
    try:
        os.chmod(_KEY_FILE, stat.S_IRUSR | stat.S_IWUSR)  # 0600 on POSIX; ignored on Windows.
    except Exception:
        pass
    return key


def _cipher() -> Fernet:
    return Fernet(_load_key())


def _load_all() -> dict[str, Any]:
    if not _VAULT_FILE.exists():
        return {"users": {}}
    try:
        blob = _VAULT_FILE.read_bytes()
        if not blob:
            return {"users": {}}
        plain = _cipher().decrypt(blob)
        data = json.loads(plain.decode("utf-8"))
        if not isinstance(data, dict):
            return {"users": {}}
        if "users" not in data or not isinstance(data["users"], dict):
            data["users"] = {}
        return data
    except (InvalidToken, ValueError):
        logger.warning("credentials_vault: existing blob unreadable — starting fresh")
        return {"users": {}}


def _save_all(data: dict[str, Any]) -> None:
    blob = _cipher().encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    _VAULT_FILE.write_bytes(blob)
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
