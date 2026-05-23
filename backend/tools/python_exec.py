"""Python code execution tool.

WARNING: This is NOT a security sandbox. Code runs in a subprocess with the same
privileges, filesystem access, and network access as the backend process. The
pattern check below is advisory logging only — it does not prevent anything.
Execution is gated by JIMAI_ENABLE_CODE_EXECUTION (off by default).
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def _execution_enabled() -> bool:
    return os.getenv("JIMAI_ENABLE_CODE_EXECUTION", "false").lower() in ("1", "true", "yes")


async def execute(code: str, timeout: int = 30) -> dict:
    """Run Python code in a subprocess and capture output.

    NOT sandboxed (see module docstring). Returns a disabled result unless
    JIMAI_ENABLE_CODE_EXECUTION is set, so the feature is opt-in everywhere it is called.
    """
    if not _execution_enabled():
        return {
            "stdout": "",
            "stderr": "Code execution is disabled. Set JIMAI_ENABLE_CODE_EXECUTION=true to enable it.",
            "returncode": -1,
            "success": False,
        }

    # Advisory only: log (does not block) operations that touch the filesystem.
    for pattern in ("open(", "write(", "shutil.", "os.remove", "os.unlink", "pathlib"):
        if pattern in code and "tmp" not in code.lower():
            logger.warning("python_exec: filesystem operation in user code: %s", pattern)

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
