"""Local-only, machine-bound encryption for data at rest.

Goal: anything on disk (chat messages, learned memory, saved credentials) must be
readable only on THIS Windows account + machine — never if the files are copied
elsewhere, and never over the network.

Primary backend: Windows DPAPI (CryptProtectData, current-user scope) via stdlib
ctypes — no third-party dependency, and the ciphertext is cryptographically bound
to this user + machine.

Fallbacks when DPAPI is unavailable (e.g. non-Windows dev box):
  1. Fernet (cryptography) with a 0600 key file, if the library is installed.
  2. Plaintext passthrough with a loud one-time warning — we never silently pretend
     to encrypt.

Stored values carry a short scheme tag so formats can coexist and pre-existing
plaintext rows are tolerated transparently:
  "D1:" + base64(dpapi blob)  |  "F1:" + fernet token  |  <anything else> = plaintext
"""
from __future__ import annotations

import base64
import logging
import os
import sys

logger = logging.getLogger(__name__)

_DPAPI_TAG = "D1:"
_FERNET_TAG = "F1:"
_warned_plaintext = False

# Lazy backend handles: None = not probed yet, False = unavailable, value = ready.
_dpapi: object = None
_fernet: object = None


# ── Windows DPAPI (preferred — no dependency, bound to user+machine) ──────────
def _load_dpapi():
    global _dpapi
    if _dpapi is not None:
        return _dpapi
    if not sys.platform.startswith("win"):
        _dpapi = False
        return _dpapi
    try:
        import ctypes
        from ctypes import wintypes

        class _BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        crypt32 = ctypes.WinDLL("crypt32.dll")
        kernel32 = ctypes.WinDLL("kernel32.dll")
        ui_forbidden = 0x1  # CRYPTPROTECT_UI_FORBIDDEN — never prompt

        def _mkblob(b: bytes) -> "_BLOB":
            buf = ctypes.create_string_buffer(b, len(b))
            return _BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

        def protect(data: bytes) -> bytes:
            inb, outb = _mkblob(data), _BLOB()
            if not crypt32.CryptProtectData(
                ctypes.byref(inb), None, None, None, None, ui_forbidden, ctypes.byref(outb)
            ):
                raise ctypes.WinError()
            out = ctypes.string_at(outb.pbData, outb.cbData)
            kernel32.LocalFree(outb.pbData)
            return out

        def unprotect(blob: bytes) -> bytes:
            inb, outb = _mkblob(blob), _BLOB()
            if not crypt32.CryptUnprotectData(
                ctypes.byref(inb), None, None, None, None, ui_forbidden, ctypes.byref(outb)
            ):
                raise ctypes.WinError()
            out = ctypes.string_at(outb.pbData, outb.cbData)
            kernel32.LocalFree(outb.pbData)
            return out

        if unprotect(protect(b"jimai-selftest")) != b"jimai-selftest":
            raise RuntimeError("DPAPI self-test mismatch")
        _dpapi = (protect, unprotect)
    except Exception as exc:  # noqa: BLE001 — any failure means fall back
        logger.warning("local_cipher: DPAPI unavailable (%s); falling back", exc)
        _dpapi = False
    return _dpapi


# ── Fernet fallback (only when DPAPI is not available) ────────────────────────
def _load_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet
    try:
        import stat

        from cryptography.fernet import Fernet

        from config.settings import PROJECT_ROOT

        key_path = PROJECT_ROOT / "data" / "memory" / ".localkey"
        key_path.parent.mkdir(parents=True, exist_ok=True)
        if key_path.exists():
            key = key_path.read_bytes()
        else:
            key = Fernet.generate_key()
            key_path.write_bytes(key)
            try:
                os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
            except Exception:
                pass
        _fernet = Fernet(key)
    except Exception:
        _fernet = False
    return _fernet


def backend() -> str:
    """Return the active backend name: 'dpapi', 'fernet', or 'plaintext'."""
    if _load_dpapi():
        return "dpapi"
    if _load_fernet():
        return "fernet"
    return "plaintext"


def is_active() -> bool:
    """True when a real encryption backend is in use (not plaintext passthrough)."""
    return backend() != "plaintext"


def is_encrypted(value: str | None) -> bool:
    return isinstance(value, str) and (value.startswith(_DPAPI_TAG) or value.startswith(_FERNET_TAG))


def encrypt_str(plain: str | None) -> str:
    """Encrypt a string for storage. Returns a scheme-tagged token (or plaintext
    if no backend is available)."""
    global _warned_plaintext
    if plain is None:
        plain = ""
    elif not isinstance(plain, str):
        plain = str(plain)
    dp = _load_dpapi()
    if dp:
        protect, _ = dp
        return _DPAPI_TAG + base64.b64encode(protect(plain.encode("utf-8"))).decode("ascii")
    fz = _load_fernet()
    if fz:
        return _FERNET_TAG + fz.encrypt(plain.encode("utf-8")).decode("ascii")
    if not _warned_plaintext:
        logger.warning("local_cipher: NO encryption backend available — data stored in PLAINTEXT")
        _warned_plaintext = True
    return plain


def decrypt_str(value: str | None) -> str:
    """Decrypt a stored value. Legacy/plaintext values are returned unchanged.

    If a value is sealed for a different user/machine (DPAPI/Fernet failure), returns
    an empty string — by design, the data is locked to the machine that wrote it.
    """
    if value is None:
        return ""
    if value.startswith(_DPAPI_TAG):
        dp = _load_dpapi()
        if not dp:
            return ""
        _, unprotect = dp
        try:
            return unprotect(base64.b64decode(value[len(_DPAPI_TAG):])).decode("utf-8")
        except Exception:
            logger.warning("local_cipher: DPAPI decrypt failed (sealed for another user/machine?)")
            return ""
    if value.startswith(_FERNET_TAG):
        fz = _load_fernet()
        if not fz:
            return ""
        try:
            return fz.decrypt(value[len(_FERNET_TAG):].encode("ascii")).decode("utf-8")
        except Exception:
            logger.warning("local_cipher: Fernet decrypt failed")
            return ""
    return value  # legacy plaintext written before encryption was enabled
