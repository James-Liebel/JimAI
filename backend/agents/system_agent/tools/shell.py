"""Shell execution helpers for the system agent."""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path

BLOCKED_COMMANDS = [
    "bcdedit",
    "bootrec",
    "del /f /s /q c:\\",
    "diskpart",
    "format",
    "net localgroup administrators",
    "net user",
    "reg delete",
    "rmdir /s /q c:\\windows",
    "rm -rf /",
    "sc delete",
]

ALWAYS_CONFIRM = [
    "del",
    "diskpart",
    "format",
    "net",
    "rd",
    "reg",
    "restart",
    "rmdir",
    "rm",
    "sc",
    "shutdown",
    "stop-process",
    "taskkill",
]

DEFAULT_TIMEOUT = 30
MAX_STDOUT_CHARS = 500_000
MAX_STDERR_CHARS = 20_000


def is_command_blocked(command: str) -> bool:
    """Return True when a command matches a blocked safety pattern."""
    lowered = str(command or "").strip().lower()
    return any(pattern in lowered for pattern in BLOCKED_COMMANDS)


def requires_confirmation(command: str) -> bool:
    """Return True when a command should always require approval."""
    lowered = str(command or "").strip().lower()
    if not lowered:
        return False
    first_token = lowered.split()[0]
    if first_token in ALWAYS_CONFIRM:
        return True
    return any(f"{token} " in lowered for token in ALWAYS_CONFIRM if " " in token)


def _truncate(text: bytes, limit: int) -> str:
    return text.decode("utf-8", errors="replace")[:limit]


async def run_command(
    command: str,
    cwd: str | None = None,
    shell: str = "powershell",
    timeout: int = DEFAULT_TIMEOUT,
    env_extras: dict | None = None,
) -> dict:
    """Run a shell command in a subprocess with timeout protection."""
    if is_command_blocked(command):
        raise PermissionError(f"Command blocked by safety policy: {command}")

    cwd_path = Path(cwd).expanduser().resolve() if cwd else Path.home()
    if not cwd_path.exists():
        raise FileNotFoundError(f"Working directory not found: {cwd_path}")

    if shell == "powershell":
        args = [
            "powershell",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ]
    elif shell == "cmd":
        args = ["cmd", "/c", command]
    elif shell == "python":
        args = ["python", "-c", command]
    else:
        args = shlex.split(command)

    env = None
    if env_extras:
        import os

        env = os.environ.copy()
        env.update({str(key): str(value) for key, value in env_extras.items()})

    import time

    started = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd_path),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        duration_ms = int((time.perf_counter() - started) * 1000)
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "returncode": -1,
            "duration_ms": duration_ms,
            "timed_out": True,
        }

    duration_ms = int((time.perf_counter() - started) * 1000)
    return {
        "stdout": _truncate(stdout, MAX_STDOUT_CHARS),
        "stderr": _truncate(stderr, MAX_STDERR_CHARS),
        "returncode": proc.returncode,
        "duration_ms": duration_ms,
        "timed_out": False,
    }


async def run_python_file(path: str, args: list[str] | None = None, cwd: str | None = None) -> dict:
    """Run a Python script file."""
    script_path = Path(path).expanduser().resolve()
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    proc = await asyncio.create_subprocess_exec(
        "python",
        str(script_path),
        *(args or []),
        cwd=str(Path(cwd).expanduser().resolve() if cwd else script_path.parent),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    return {
        "stdout": _truncate(stdout, MAX_STDOUT_CHARS),
        "stderr": _truncate(stderr, MAX_STDERR_CHARS),
        "returncode": proc.returncode,
    }


async def run_powershell_file(path: str, args: list[str] | None = None) -> dict:
    """Run a PowerShell script file."""
    script_path = Path(path).expanduser().resolve()
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    proc = await asyncio.create_subprocess_exec(
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        *(args or []),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    return {
        "stdout": _truncate(stdout, MAX_STDOUT_CHARS),
        "stderr": _truncate(stderr, MAX_STDERR_CHARS),
        "returncode": proc.returncode,
    }
