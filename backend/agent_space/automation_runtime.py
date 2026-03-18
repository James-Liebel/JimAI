"""Local automation runtime manager for n8n."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import shutil
import signal
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from .config import SettingsStore
from .paths import DATA_ROOT, PROJECT_ROOT, RUNTIME_DIR, ensure_layout

STATE_FILE = RUNTIME_DIR / "n8n_runtime.json"
DEFAULT_INSTALL_ROOT = DATA_ROOT / "tools" / "n8n"


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_pid(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        os.kill(pid, signal.SIGTERM)
        return True
    except Exception:
        return False


class N8nRuntimeManager:
    """Manages optional local n8n process for workflow automation."""

    def __init__(self, *, settings_store: SettingsStore) -> None:
        ensure_layout()
        self._settings = settings_store
        self._lock = asyncio.Lock()
        self._managed_pid: int | None = None
        self._last_started_at = 0.0
        self._last_error = ""
        self._last_command: list[str] = []
        self._load_state()

    def _load_state(self) -> None:
        if not STATE_FILE.exists():
            self._persist_state_locked()
            return
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        pid = int(data.get("managed_pid") or 0)
        self._managed_pid = pid if pid > 0 else None
        self._last_started_at = float(data.get("last_started_at") or 0.0)
        self._last_error = str(data.get("last_error") or "")
        raw_cmd = data.get("last_command") or []
        self._last_command = [str(part) for part in raw_cmd] if isinstance(raw_cmd, list) else []
        self._persist_state_locked()

    def _persist_state_locked(self) -> None:
        payload = {
            "managed_pid": self._managed_pid,
            "last_started_at": self._last_started_at,
            "last_error": self._last_error,
            "last_command": self._last_command,
            "updated_at": time.time(),
        }
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.warning("Failed to persist n8n manager state to '%s'", STATE_FILE, exc_info=True)

    @staticmethod
    def _normalize_url(url: str, port: int) -> str:
        cleaned = str(url or "").strip() or f"http://localhost:{int(port)}"
        if not cleaned.startswith(("http://", "https://")):
            cleaned = f"http://{cleaned}"
        parsed = urllib.parse.urlparse(cleaned)
        if not parsed.netloc:
            cleaned = f"http://localhost:{int(port)}"
        return cleaned.rstrip("/")

    async def startup(self) -> None:
        cfg = self._settings.get()
        if not bool(cfg.get("automation_n8n_enabled", True)):
            return
        if not bool(cfg.get("automation_n8n_auto_start", False)):
            return
        if str(cfg.get("automation_n8n_mode", "managed")) != "managed":
            return
        try:
            await self.start()
        except Exception:
            logger.warning("n8n auto-start during startup failed; service will remain stopped", exc_info=True)

    async def shutdown(self) -> None:
        cfg = self._settings.get()
        if not bool(cfg.get("automation_n8n_stop_on_shutdown", True)):
            return
        await self.stop()

    @staticmethod
    def _probe_url_once(url: str) -> bool:
        candidates = [f"{url}/healthz", f"{url}/healthz/readiness", url]
        for probe in candidates:
            req = urllib.request.Request(probe, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    if int(resp.status) < 500:
                        return True
            except urllib.error.HTTPError as exc:
                if 200 <= int(exc.code) < 500:
                    return True
            except Exception:
                continue
        return False

    async def _probe_url(self, url: str) -> bool:
        return await asyncio.to_thread(self._probe_url_once, url)

    def _resolve_start_command(self, cfg: dict[str, Any]) -> list[str]:
        custom = str(cfg.get("automation_n8n_start_command", "") or "").strip()
        port = int(cfg.get("automation_n8n_port", 5678))
        if custom:
            return shlex.split(custom, posix=(os.name != "nt"))

        configured_root = str(cfg.get("automation_n8n_install_path", "") or "").strip()
        install_root = Path(configured_root).expanduser().resolve() if configured_root else DEFAULT_INSTALL_ROOT.resolve()
        local_bin = install_root / "node_modules" / ".bin" / ("n8n.cmd" if os.name == "nt" else "n8n")
        if local_bin.exists():
            return [str(local_bin), "start", "--port", str(port)]

        if os.name == "nt":
            global_n8n = shutil.which("n8n.cmd")
            if global_n8n:
                return [global_n8n, "start", "--port", str(port)]
            npx_bin = shutil.which("npx.cmd")
            if npx_bin:
                return [npx_bin, "n8n", "start", "--port", str(port)]
        else:
            global_n8n = shutil.which("n8n")
            if global_n8n:
                return [global_n8n, "start", "--port", str(port)]
            npx_bin = shutil.which("npx")
            if npx_bin:
                return [npx_bin, "n8n", "start", "--port", str(port)]
        raise RuntimeError(
            "n8n command not found. Install with 'npm install -g n8n' "
            "or use Automation tab -> Install Local n8n."
        )

    async def status(self) -> dict[str, Any]:
        cfg = self._settings.get()
        mode = str(cfg.get("automation_n8n_mode", "managed") or "managed").strip() or "managed"
        port = int(cfg.get("automation_n8n_port", 5678))
        base_url = self._normalize_url(str(cfg.get("automation_n8n_url", "")), port)
        async with self._lock:
            managed_pid = int(self._managed_pid or 0)
            if managed_pid and not _pid_running(managed_pid):
                self._managed_pid = None
                managed_pid = 0
                self._persist_state_locked()
            last_error = self._last_error
            started_at = self._last_started_at
            last_command = list(self._last_command)
        reachable = await self._probe_url(base_url)
        return {
            "enabled": bool(cfg.get("automation_n8n_enabled", True)),
            "mode": mode,
            "url": base_url,
            "port": port,
            "auto_start": bool(cfg.get("automation_n8n_auto_start", False)),
            "stop_on_shutdown": bool(cfg.get("automation_n8n_stop_on_shutdown", True)),
            "managed_pid": managed_pid or None,
            "managed_running": bool(managed_pid and _pid_running(managed_pid)),
            "reachable": bool(reachable),
            "last_error": last_error,
            "last_started_at": started_at,
            "last_command": last_command,
            "install_path": str(cfg.get("automation_n8n_install_path", "") or str(DEFAULT_INSTALL_ROOT)),
        }

    async def start(self, *, force: bool = False) -> dict[str, Any]:
        cfg = self._settings.get()
        if not bool(cfg.get("automation_n8n_enabled", True)):
            raise RuntimeError("Automation n8n integration is disabled in settings.")
        if str(cfg.get("automation_n8n_mode", "managed")) != "managed":
            raise RuntimeError("n8n mode is 'external'. Switch to 'managed' to start n8n from jimAI.")

        port = int(cfg.get("automation_n8n_port", 5678))
        base_url = self._normalize_url(str(cfg.get("automation_n8n_url", "")), port)
        async with self._lock:
            existing_pid = int(self._managed_pid or 0)
        if existing_pid and _pid_running(existing_pid) and not force:
            status = await self.status()
            status["started"] = False
            status["message"] = f"Managed n8n already running (PID {existing_pid})."
            return status

        command = self._resolve_start_command(cfg)
        env = os.environ.copy()
        env["N8N_PORT"] = str(port)
        env.setdefault("N8N_HOST", "0.0.0.0")
        env.setdefault("N8N_PROTOCOL", "http")
        env.setdefault("N8N_SECURE_COOKIE", "false")
        env.setdefault("N8N_USER_FOLDER", str((DATA_ROOT / "n8n").resolve()))
        env.setdefault("N8N_EDITOR_BASE_URL", base_url)

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        try:
            proc = subprocess.Popen(
                command,
                cwd=str(PROJECT_ROOT),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except Exception as exc:
            async with self._lock:
                self._last_error = f"Failed to start n8n: {exc}"
                self._persist_state_locked()
            raise RuntimeError(f"Failed to start n8n: {exc}") from exc

        async with self._lock:
            self._managed_pid = int(proc.pid)
            self._last_started_at = time.time()
            self._last_error = ""
            self._last_command = list(command)
            self._persist_state_locked()

        timeout_seconds = max(5, int(cfg.get("automation_n8n_start_timeout_seconds", 45)))
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if await self._probe_url(base_url):
                status = await self.status()
                status["started"] = True
                status["message"] = "n8n started and reachable."
                return status
            await asyncio.sleep(0.6)

        status = await self.status()
        status["started"] = True
        status["message"] = "n8n process started but URL not reachable yet."
        return status

    async def stop(self) -> dict[str, Any]:
        async with self._lock:
            pid = int(self._managed_pid or 0)
            self._managed_pid = None
            self._persist_state_locked()
        if pid:
            stopped = _kill_pid(pid)
            if not stopped:
                async with self._lock:
                    self._last_error = f"Unable to stop n8n PID {pid}."
                    self._persist_state_locked()
            status = await self.status()
            status["stopped"] = bool(stopped)
            status["stopped_pid"] = pid
            return status
        status = await self.status()
        status["stopped"] = False
        status["message"] = "No managed n8n process was running."
        return status

    async def install_local(self, *, set_as_default: bool = True) -> dict[str, Any]:
        cfg = self._settings.get()
        configured_root = str(cfg.get("automation_n8n_install_path", "") or "").strip()
        install_root = Path(configured_root).expanduser().resolve() if configured_root else DEFAULT_INSTALL_ROOT.resolve()
        install_root.mkdir(parents=True, exist_ok=True)

        npm_bin = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if not npm_bin:
            raise RuntimeError("npm is required to install local n8n but was not found in PATH.")

        command = [npm_bin, "install", "n8n", "--no-fund", "--no-audit", "--prefix", str(install_root)]

        def _run_install() -> tuple[int, str, str]:
            proc = subprocess.run(
                command,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=1800,
            )
            return proc.returncode, proc.stdout, proc.stderr

        code, stdout, stderr = await asyncio.to_thread(_run_install)
        if code != 0:
            snippet = (stderr or stdout or "").strip()
            if len(snippet) > 800:
                snippet = snippet[-800:]
            raise RuntimeError(f"Local n8n install failed: {snippet or 'unknown error'}")

        local_bin = install_root / "node_modules" / ".bin" / ("n8n.cmd" if os.name == "nt" else "n8n")
        updates: dict[str, Any] = {"automation_n8n_install_path": str(install_root)}
        if set_as_default and local_bin.exists():
            port = int(cfg.get("automation_n8n_port", 5678))
            updates["automation_n8n_start_command"] = f"\"{local_bin}\" start --port {port}"
            updates["automation_n8n_mode"] = "managed"
        self._settings.update(updates)

        status = await self.status()
        status["installed"] = True
        status["install_root"] = str(install_root)
        status["stdout_tail"] = (stdout or "")[-1000:]
        return status
