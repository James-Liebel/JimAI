"""Test runner tool — detects and runs pytest or jest."""

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _detect_framework(path: str) -> str:
    """Detect if the project uses pytest or jest."""
    p = Path(path)
    # Check for Python test files
    if list(p.rglob("test_*.py")) or list(p.rglob("*_test.py")):
        return "pytest"
    # Check for package.json with jest
    pkg = p / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text())
            deps = {**data.get("devDependencies", {}), **data.get("dependencies", {})}
            if "jest" in deps or "jest" in data.get("scripts", {}).get("test", ""):
                return "jest"
        except Exception:
            pass
    return "pytest"  # default


async def run_tests(path: str = ".") -> dict:
    """Run tests and return structured results."""
    framework = _detect_framework(path)

    if framework == "pytest":
        cmd = ["python", "-m", "pytest", "--tb=short", "-q", path]
    else:
        cmd = ["npx", "jest", "--ci", "--json", path]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=path if Path(path).is_dir() else None,
        )

        output = result.stdout + result.stderr

        # Parse pytest output
        if framework == "pytest":
            passed = output.count(" passed")
            failed = output.count(" failed")
            errors = []
            for line in output.split("\n"):
                if "FAILED" in line or "ERROR" in line:
                    errors.append(line.strip())
            return {
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "success": result.returncode == 0,
                "output": output[-2000:],  # last 2000 chars
                "framework": "pytest",
            }
        else:
            # Parse jest JSON output
            try:
                jest_data = json.loads(result.stdout)
                return {
                    "passed": jest_data.get("numPassedTests", 0),
                    "failed": jest_data.get("numFailedTests", 0),
                    "errors": [
                        tr["message"]
                        for tr in jest_data.get("testResults", [])
                        if tr.get("status") == "failed"
                    ],
                    "success": jest_data.get("success", False),
                    "output": output[-2000:],
                    "framework": "jest",
                }
            except json.JSONDecodeError:
                return {
                    "passed": 0,
                    "failed": 1,
                    "errors": [output[-500:]],
                    "success": False,
                    "output": output[-2000:],
                    "framework": "jest",
                }

    except subprocess.TimeoutExpired:
        return {
            "passed": 0,
            "failed": 0,
            "errors": ["Test execution timed out after 120 seconds"],
            "success": False,
            "output": "",
            "framework": framework,
        }
    except Exception as exc:
        return {
            "passed": 0,
            "failed": 0,
            "errors": [str(exc)],
            "success": False,
            "output": "",
            "framework": framework,
        }
