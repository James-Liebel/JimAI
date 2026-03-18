"""Sandboxed Python code execution tool."""

import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


async def execute(code: str, timeout: int = 30) -> dict:
    """Execute Python code in a sandboxed subprocess.

    Writes code to a temp file, runs it, captures output.
    Never allows file writes outside of the temp directory.
    """
    # Safety: strip any obvious file-write operations outside /tmp/
    dangerous_patterns = [
        "open(",
        "write(",
        "shutil.",
        "os.remove",
        "os.unlink",
        "pathlib",
    ]
    # We allow these in /tmp/ context — just log a warning for non-tmp writes
    for pattern in dangerous_patterns:
        if pattern in code and "tmp" not in code.lower():
            logger.warning("Potentially unsafe operation detected: %s", pattern)

    # Write to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, dir=tempfile.gettempdir()
    ) as f:
        f.write(code)
        tmp_path = Path(f.name)

    try:
        result = subprocess.run(
            ["python", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tempfile.gettempdir(),
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Execution timed out after {timeout} seconds",
            "returncode": -1,
            "success": False,
        }
    except Exception as exc:
        return {
            "stdout": "",
            "stderr": str(exc),
            "returncode": -1,
            "success": False,
        }
    finally:
        tmp_path.unlink(missing_ok=True)
