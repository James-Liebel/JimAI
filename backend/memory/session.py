"""In-memory session store — tracks conversation history per chat (session_id = chat id).

History is scoped to each chat window: only the active chat's history is used when
generating replies. Other chats stay saved (see chat_store) until the user deletes them.
"""

import os
import time
from typing import Any

# session_id (chat id) → session data
_sessions: dict[str, dict[str, Any]] = {}

# Server-side cap (client still holds full thread in saved JSON); raise for long context + rolling summary
MAX_HISTORY = max(20, int(os.getenv("CHAT_SESSION_MAX_MESSAGES", "160")))


def get_session(session_id: str) -> dict[str, Any]:
    """Return or create a session."""
    if session_id not in _sessions:
        _sessions[session_id] = {
            "messages": [],
            "sources": [],
            "created_at": time.time(),
            "rolling_summary": "",
        }
    return _sessions[session_id]


def add_message(
    session_id: str, role: str, content: str, mode: str = "chat"
) -> None:
    """Append a message to the session, enforcing the history cap."""
    session = get_session(session_id)
    session["messages"].append({
        "role": role,
        "content": content,
        "mode": mode,
        "timestamp": time.time(),
    })
    # Keep only the most recent messages
    if len(session["messages"]) > MAX_HISTORY:
        session["messages"] = session["messages"][-MAX_HISTORY:]


def update_session(session_id: str, key: str, value: Any) -> None:
    """Set an arbitrary key on the session."""
    session = get_session(session_id)
    session[key] = value


def clear_session(session_id: str) -> None:
    """Remove a session entirely."""
    _sessions.pop(session_id, None)


def get_history(session_id: str) -> list[dict]:
    """Return the message history for a session."""
    return get_session(session_id)["messages"]


def add_source(session_id: str, source: str) -> None:
    """Track that a source was ingested during this session."""
    session = get_session(session_id)
    if source not in session["sources"]:
        session["sources"].append(source)


def get_sources(session_id: str) -> list[str]:
    """Return sources ingested during this session."""
    return get_session(session_id).get("sources", [])
