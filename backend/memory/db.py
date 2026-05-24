"""SQLite-backed persistence for chats, messages, users, and per-user memory.

A single file (data/memory/jimai.sqlite) holds normalized rows so the app
scales past the per-file JSON approach: list/search by indexed columns
instead of globbing and parsing every chat file.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from config.settings import PROJECT_ROOT

from . import local_cipher as cipher

DB_PATH: Path = PROJECT_ROOT / "data" / "memory" / "jimai.sqlite"
DEFAULT_USER_ID = "default"

_LOCK = threading.RLock()
_conn: sqlite3.Connection | None = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          TEXT PRIMARY KEY,
    label       TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS chats (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL DEFAULT 'default',
    title         TEXT NOT NULL DEFAULT '',
    preview       TEXT NOT NULL DEFAULT '',
    message_count INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_chats_user_updated
    ON chats(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chats_updated
    ON chats(updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    TEXT NOT NULL,
    seq        INTEGER NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    mode       TEXT NOT NULL DEFAULT 'chat',
    timestamp  REAL NOT NULL,
    extra      TEXT,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_chat_seq
    ON messages(chat_id, seq);
CREATE INDEX IF NOT EXISTS idx_messages_chat_ts
    ON messages(chat_id, timestamp);

CREATE TABLE IF NOT EXISTS user_memory (
    user_id     TEXT NOT NULL,
    slot        TEXT NOT NULL,
    data        TEXT NOT NULL,
    updated_at  REAL NOT NULL,
    PRIMARY KEY (user_id, slot)
);
"""


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # Zero out freed content so deleted/updated plaintext doesn't linger in free pages.
    conn.execute("PRAGMA secure_delete=ON")
    conn.executescript(_SCHEMA)
    _ensure_user(conn, DEFAULT_USER_ID)
    _conn = conn
    _encrypt_existing_rows(conn)
    return conn


_ENC_MARK = "_encrypted_at_rest_v1"


def _encrypt_existing_rows(conn: sqlite3.Connection) -> None:
    """One-shot: encrypt any pre-existing plaintext rows so old data is protected too.

    Idempotent (guarded by a mark slot) and a no-op when no encryption backend is
    available. The interpolated parts below are fixed column names, never user input.
    """
    if not cipher.is_active():
        return
    done = conn.execute(
        "SELECT 1 FROM user_memory WHERE user_id = ? AND slot = ?",
        (DEFAULT_USER_ID, _ENC_MARK),
    ).fetchone()
    if done is not None:
        return
    for row in conn.execute("SELECT id, content, extra FROM messages").fetchall():
        updates: dict[str, str] = {}
        if not cipher.is_encrypted(row["content"]):
            updates["content"] = cipher.encrypt_str(row["content"])
        if row["extra"] is not None and not cipher.is_encrypted(row["extra"]):
            updates["extra"] = cipher.encrypt_str(row["extra"])
        if updates:
            sets = ", ".join(f"{col} = ?" for col in updates)
            conn.execute(f"UPDATE messages SET {sets} WHERE id = ?", (*updates.values(), row["id"]))
    for row in conn.execute("SELECT id, title, preview FROM chats").fetchall():
        updates = {}
        if not cipher.is_encrypted(row["title"]):
            updates["title"] = cipher.encrypt_str(row["title"])
        if not cipher.is_encrypted(row["preview"]):
            updates["preview"] = cipher.encrypt_str(row["preview"])
        if updates:
            sets = ", ".join(f"{col} = ?" for col in updates)
            conn.execute(f"UPDATE chats SET {sets} WHERE id = ?", (*updates.values(), row["id"]))
    for row in conn.execute("SELECT user_id, slot, data FROM user_memory").fetchall():
        if not cipher.is_encrypted(row["data"]):
            conn.execute(
                "UPDATE user_memory SET data = ? WHERE user_id = ? AND slot = ?",
                (cipher.encrypt_str(row["data"]), row["user_id"], row["slot"]),
            )
    conn.execute(
        "INSERT OR REPLACE INTO user_memory(user_id, slot, data, updated_at) VALUES(?,?,?,?)",
        (DEFAULT_USER_ID, _ENC_MARK, cipher.encrypt_str("1"), time.time()),
    )
    # Purge plaintext residue left by the in-place UPDATEs: flush+truncate the WAL,
    # then rebuild the file so no freed page still holds the old cleartext.
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("VACUUM")


def _ensure_user(conn: sqlite3.Connection, user_id: str, label: str = "") -> None:
    conn.execute(
        "INSERT OR IGNORE INTO users(id, label, created_at) VALUES(?, ?, ?)",
        (user_id, label, time.time()),
    )


def get_conn() -> sqlite3.Connection:
    with _LOCK:
        return _connect()


def ensure_user(user_id: str, label: str = "") -> None:
    conn = get_conn()
    with _LOCK:
        _ensure_user(conn, user_id, label)


# ── Chats ────────────────────────────────────────────────────────────

def upsert_chat(
    chat_id: str,
    title: str,
    messages: list[dict[str, Any]],
    user_id: str = DEFAULT_USER_ID,
) -> dict[str, Any]:
    conn = get_conn()
    now = time.time()
    preview = ""
    for m in messages:
        if m.get("role") == "user" and m.get("content"):
            preview = str(m["content"])[:120]
            break
    with _LOCK:
        _ensure_user(conn, user_id)
        row = conn.execute(
            "SELECT created_at FROM chats WHERE id = ?", (chat_id,)
        ).fetchone()
        created_at = row["created_at"] if row else now
        conn.execute(
            """
            INSERT INTO chats(id, user_id, title, preview, message_count, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                user_id=excluded.user_id,
                title=excluded.title,
                preview=excluded.preview,
                message_count=excluded.message_count,
                updated_at=excluded.updated_at
            """,
            (chat_id, user_id, cipher.encrypt_str(title), cipher.encrypt_str(preview), len(messages), created_at, now),
        )
        # Re-write the messages for this chat. Cheap (a chat is small), and keeps
        # storage in sync with the canonical client-side thread.
        conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        rows = []
        for i, m in enumerate(messages):
            role = str(m.get("role") or "")
            content = str(m.get("content") or "")
            mode = str(m.get("mode") or "chat")
            ts = float(m.get("timestamp") or now)
            extra = {k: v for k, v in m.items() if k not in {"role", "content", "mode", "timestamp"}}
            enc_extra = cipher.encrypt_str(json.dumps(extra, ensure_ascii=False)) if extra else None
            rows.append((chat_id, i, role, cipher.encrypt_str(content), mode, ts, enc_extra))
        if rows:
            conn.executemany(
                "INSERT INTO messages(chat_id, seq, role, content, mode, timestamp, extra) VALUES(?,?,?,?,?,?,?)",
                rows,
            )
    return {
        "id": chat_id,
        "title": title,
        "messages": messages,
        "created_at": created_at,
        "updated_at": now,
        "user_id": user_id,
    }


def load_chat_row(chat_id: str) -> dict[str, Any] | None:
    conn = get_conn()
    with _LOCK:
        chat = conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()
        if chat is None:
            return None
        msg_rows = conn.execute(
            "SELECT role, content, mode, timestamp, extra FROM messages WHERE chat_id = ? ORDER BY seq",
            (chat_id,),
        ).fetchall()
    messages: list[dict[str, Any]] = []
    for r in msg_rows:
        msg = {"role": r["role"], "content": cipher.decrypt_str(r["content"]), "mode": r["mode"], "timestamp": r["timestamp"]}
        if r["extra"]:
            try:
                extra = json.loads(cipher.decrypt_str(r["extra"]))
                if isinstance(extra, dict):
                    msg.update(extra)
            except Exception:
                pass
        messages.append(msg)
    return {
        "id": chat["id"],
        "title": cipher.decrypt_str(chat["title"]),
        "messages": messages,
        "created_at": chat["created_at"],
        "updated_at": chat["updated_at"],
        "user_id": chat["user_id"],
    }


def delete_chat_row(chat_id: str) -> bool:
    conn = get_conn()
    with _LOCK:
        cur = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        return cur.rowcount > 0


def list_chats_rows(user_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    conn = get_conn()
    with _LOCK:
        if user_id is None:
            rows = conn.execute(
                "SELECT id, title, preview, message_count, created_at, updated_at, user_id "
                "FROM chats ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, preview, message_count, created_at, updated_at, user_id "
                "FROM chats WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["title"] = cipher.decrypt_str(d.get("title"))
        d["preview"] = cipher.decrypt_str(d.get("preview"))
        out.append(d)
    return out


# ── Per-user memory slots ────────────────────────────────────────────

def read_user_slot(user_id: str, slot: str) -> dict[str, Any] | None:
    conn = get_conn()
    with _LOCK:
        row = conn.execute(
            "SELECT data, updated_at FROM user_memory WHERE user_id = ? AND slot = ?",
            (user_id, slot),
        ).fetchone()
    if row is None:
        return None
    try:
        return {"data": json.loads(cipher.decrypt_str(row["data"])), "updated_at": row["updated_at"]}
    except Exception:
        return None


def write_user_slot(user_id: str, slot: str, data: Any) -> None:
    conn = get_conn()
    payload = cipher.encrypt_str(json.dumps(data, ensure_ascii=False))
    now = time.time()
    with _LOCK:
        _ensure_user(conn, user_id)
        conn.execute(
            """
            INSERT INTO user_memory(user_id, slot, data, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(user_id, slot) DO UPDATE SET
                data=excluded.data,
                updated_at=excluded.updated_at
            """,
            (user_id, slot, payload, now),
        )


def delete_user_slot(user_id: str, slot: str) -> None:
    """Remove a per-user memory slot. No-op if it doesn't exist."""
    conn = get_conn()
    with _LOCK:
        conn.execute(
            "DELETE FROM user_memory WHERE user_id = ? AND slot = ?",
            (user_id, slot),
        )


# ── One-shot JSON migration ──────────────────────────────────────────

_MIGRATION_MARK = "_migrated_json_chats_v1"


def migrate_json_chats_if_needed(legacy_dir: Path) -> int:
    """Import any data/chats/*.json files into SQLite once. Returns count imported."""
    conn = get_conn()
    with _LOCK:
        already = conn.execute(
            "SELECT 1 FROM user_memory WHERE user_id = ? AND slot = ?",
            (DEFAULT_USER_ID, _MIGRATION_MARK),
        ).fetchone()
    if already is not None:
        return 0
    imported = 0
    if legacy_dir.exists():
        for path in legacy_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            chat_id = str(data.get("id") or path.stem)
            title = str(data.get("title") or "")
            messages = list(data.get("messages") or [])
            # Preserve original timestamps by writing then patching created_at/updated_at.
            upsert_chat(chat_id, title, messages, user_id=DEFAULT_USER_ID)
            created = float(data.get("created_at") or time.time())
            updated = float(data.get("updated_at") or created)
            with _LOCK:
                conn.execute(
                    "UPDATE chats SET created_at = ?, updated_at = ? WHERE id = ?",
                    (created, updated, chat_id),
                )
            imported += 1
    write_user_slot(DEFAULT_USER_ID, _MIGRATION_MARK, {"imported": imported, "at": time.time()})
    return imported


def iter_recent_messages(user_id: str, limit: int = 200) -> Iterable[dict[str, Any]]:
    """Stream a user's recent messages across all their chats (for learning jobs)."""
    conn = get_conn()
    with _LOCK:
        rows = conn.execute(
            """
            SELECT m.role, m.content, m.timestamp, m.chat_id
            FROM messages m
            JOIN chats c ON c.id = m.chat_id
            WHERE c.user_id = ?
            ORDER BY m.timestamp DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    for r in rows:
        d = dict(r)
        d["content"] = cipher.decrypt_str(d.get("content"))
        yield d
