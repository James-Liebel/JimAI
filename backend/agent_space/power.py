"""System power state controls for Agent Space."""

from __future__ import annotations

import json
import logging
import time
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

from models import ollama_client

from .paths import DATA_ROOT, ensure_layout

POWER_FILE = DATA_ROOT / "power.json"

DEFAULT_POWER_STATE = {
    "enabled": True,
    "release_gpu_on_off": False,
    "updated_at": 0.0,
}


class PowerManager:
    """Tracks ON/OFF state and optional GPU release behavior."""

    def __init__(self) -> None:
        ensure_layout()
        self._lock = Lock()
        self._state_override: dict[str, Any] | None = None
        if not POWER_FILE.exists():
            self._persist_state(dict(DEFAULT_POWER_STATE))

    def _persist_state(self, state: dict[str, Any], retries: int = 3, delay_seconds: float = 0.05) -> bool:
        payload = json.dumps(state, indent=2)
        for attempt in range(retries + 1):
            try:
                POWER_FILE.write_text(payload, encoding="utf-8")
                self._state_override = None
                return True
            except PermissionError:
                if attempt < retries:
                    time.sleep(delay_seconds)
                    continue
                self._state_override = dict(state)
                return False
            except Exception:
                self._state_override = dict(state)
                return False
        return False

    def get_state(self) -> dict[str, Any]:
        try:
            data = json.loads(POWER_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = dict(DEFAULT_POWER_STATE)
        merged = dict(DEFAULT_POWER_STATE)
        merged.update(data)
        if self._state_override:
            merged.update(self._state_override)
        return merged

    async def set_state(self, enabled: bool, release_gpu_on_off: bool | None = None) -> dict[str, Any]:
        with self._lock:
            state = self.get_state()
            state["enabled"] = enabled
            if release_gpu_on_off is not None:
                state["release_gpu_on_off"] = bool(release_gpu_on_off)
            state["updated_at"] = time.time()
            self._persist_state(state)

        if not enabled and state.get("release_gpu_on_off"):
            try:
                await ollama_client.unload_all_models()
            except Exception:
                # Graceful fallback: state update should still succeed if Ollama is down.
                logger.warning("Failed to unload Ollama models on power-off; Ollama may be unavailable", exc_info=True)
        return state

    def is_enabled(self) -> bool:
        return bool(self.get_state().get("enabled", True))
