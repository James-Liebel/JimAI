"""Git CLI wrapper tool."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _run_git(args: list[str], cwd: str | None = None) -> dict:
    """Run a git command and return structured output."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=cwd,
        )
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "success": result.returncode == 0,
        }
    except Exception as exc:
        return {"stdout": "", "stderr": str(exc), "success": False}


async def status(cwd: str | None = None) -> str:
    """Return git status output."""
    result = _run_git(["status", "--short"], cwd=cwd)
    return result["stdout"] if result["success"] else result["stderr"]


async def diff(staged: bool = False, cwd: str | None = None) -> str:
    """Return git diff output."""
    args = ["diff"]
    if staged:
        args.append("--staged")
    result = _run_git(args, cwd=cwd)
    return result["stdout"] if result["success"] else result["stderr"]


async def log(n: int = 10, cwd: str | None = None) -> list[dict]:
    """Return recent git log entries."""
    result = _run_git(
        ["log", f"-{n}", "--pretty=format:%H|%an|%ae|%s|%ci"],
        cwd=cwd,
    )
    if not result["success"] or not result["stdout"]:
        return []

    entries = []
    for line in result["stdout"].split("\n"):
        parts = line.split("|", 4)
        if len(parts) == 5:
            entries.append({
                "hash": parts[0],
                "author": parts[1],
                "email": parts[2],
                "message": parts[3],
                "date": parts[4],
            })
    return entries


async def add(paths: list[str], cwd: str | None = None) -> str:
    """Stage files for commit."""
    result = _run_git(["add"] + paths, cwd=cwd)
    return "Staged" if result["success"] else result["stderr"]


async def commit(message: str, cwd: str | None = None) -> str:
    """Create a commit with the given message."""
    result = _run_git(["commit", "-m", message], cwd=cwd)
    return result["stdout"] if result["success"] else result["stderr"]


async def push(cwd: str | None = None) -> str:
    """Push to remote."""
    result = _run_git(["push"], cwd=cwd)
    return result["stdout"] if result["success"] else result["stderr"]
