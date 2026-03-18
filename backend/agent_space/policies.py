"""Shell command policy gates for Agent Space."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any

SAFE_PREFIXES = {
    "dir",
    "type",
    "echo",
    "python",
    "python.exe",
    "pytest",
    "pip",
    "git",
    "npm",
    "node",
    "npx",
    "uvicorn",
    "where",
    "find",
    "rg",
}

DEV_PREFIXES = SAFE_PREFIXES | {
    "pnpm",
    "yarn",
    "tsc",
}

BLOCKED_FRAGMENTS = (
    "rm -rf",
    "rmdir /s",
    "del /f",
    "format ",
    "diskpart",
    "shutdown",
    "reboot",
    "poweroff",
    "git reset --hard",
    "git checkout --",
)

BLOCKED_CHAIN_TOKENS = (
    "&&",
    "||",
    "|",
    ";",
)

RISKY_INLINE_PYTHON_FRAGMENTS = (
    "import socket",
    "import requests",
    "import httpx",
    "import urllib",
    "import subprocess",
    "subprocess.",
    "os.system(",
    "os.popen(",
    "shutil.rmtree(",
)


class PolicyError(RuntimeError):
    """Raised when command policy blocks a request."""


def _normalize_prefix(command: str) -> str:
    first = (command or "").strip().split(maxsplit=1)
    return first[0].lower() if first else ""


def _is_path_inside(path: Path, root: Path) -> bool:
    try:
        return str(path.resolve()).startswith(str(root.resolve()))
    except Exception:
        return False


def validate_command(command: str, profile: str, cwd: str, repo_root: Path, allow_shell: bool) -> None:
    """Validate a command against policy profile and path bounds."""
    if not allow_shell:
        raise PolicyError("Shell execution is disabled by policy.")
    raw_command = (command or "").strip()
    normalized = raw_command.lower()
    if not normalized:
        raise PolicyError("Empty command.")
    for blocked in BLOCKED_FRAGMENTS:
        if blocked in normalized:
            raise PolicyError(f"Blocked command fragment: '{blocked}'.")

    cwd_path = Path(cwd).resolve()
    if not _is_path_inside(cwd_path, repo_root):
        raise PolicyError("Command cwd is outside repository.")

    prefix = _normalize_prefix(command)
    if profile == "safe" and prefix not in SAFE_PREFIXES:
        raise PolicyError(f"Prefix '{prefix}' is not allowed in safe profile.")
    if profile == "dev" and prefix not in DEV_PREFIXES:
        raise PolicyError(f"Prefix '{prefix}' is not allowed in dev profile.")
    if profile not in {"safe", "dev", "unrestricted"}:
        raise PolicyError(f"Unknown command profile '{profile}'.")

    if profile in {"safe", "dev"}:
        for token in BLOCKED_CHAIN_TOKENS:
            if token in raw_command:
                raise PolicyError(f"Command chaining token '{token}' is not allowed in {profile} profile.")

    if profile == "safe" and prefix in {"python", "python.exe"} and "-c" in normalized:
        for fragment in RISKY_INLINE_PYTHON_FRAGMENTS:
            if fragment in normalized:
                raise PolicyError(f"Risky inline python fragment '{fragment}' is not allowed in safe profile.")


async def run_command(
    command: str,
    cwd: str,
    profile: str,
    repo_root: Path,
    allow_shell: bool,
    timeout: int = 120,
) -> dict[str, Any]:
    """Run a command after policy validation."""
    validate_command(command, profile, cwd, repo_root, allow_shell)

    def _run() -> subprocess.CompletedProcess:
        return subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
            env=os.environ.copy(),
        )

    try:
        result = await asyncio.to_thread(_run)
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds.",
        }
    except Exception as exc:
        return {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": str(exc),
        }

    return {
        "success": result.returncode == 0,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
