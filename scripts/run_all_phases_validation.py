"""Purpose: Run full jimAI phase validation suite. Date: 2026-03-10."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def run_step(
    name: str,
    command: list[str],
    cwd: Path,
    capture_output: bool = True,
    env_overrides: dict[str, str] | None = None,
) -> bool:
    print(f"[STEP] {name}")
    env = None
    if env_overrides:
        env = dict(os.environ)
        env.update(env_overrides)
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=capture_output,
        text=True,
        env=env,
    )
    if capture_output:
        if proc.stdout.strip():
            print(proc.stdout.strip())
        if proc.stderr.strip():
            print(proc.stderr.strip())
    ok = proc.returncode == 0
    print(f"[RESULT] {name}: {'PASS' if ok else 'FAIL'}")
    print("-" * 72)
    return ok


def main() -> int:
    python = str(BACKEND / ".venv" / "Scripts" / "python.exe")
    steps = [
        ("Backend import sanity", [python, "test_import.py"], BACKEND, True),
        ("Agent Space core validation", [python, "tests/agent_space_validation.py"], BACKEND, True),
        (
            "Agent team validation",
            [python, "tests/agent_space_team_validation.py"],
            BACKEND,
            True,
            {"AGENT_SPACE_TEAM_VALIDATION_TIMEOUT": "180"},
        ),
        ("System audit validation", [python, "tests/agent_space_system_audit_validation.py"], BACKEND, True),
        ("Chat live lookup validation", [python, "tests/agent_space_chat_live_lookup_validation.py"], BACKEND, True),
        ("Continue-on-failure validation", [python, "tests/agent_space_continue_on_failure_validation.py"], BACKEND, True),
        ("Planner recovery validation", [python, "tests/agent_space_planner_recovery_validation.py"], BACKEND, True),
        # Use TS compile only here. esbuild/vite may fail with spawn EPERM under sandboxed subprocesses.
        ("Frontend compile sanity (tsc)", ["cmd.exe", "/c", "npx tsc --noEmit"], FRONTEND, True, None),
    ]

    failed = 0
    for step in steps:
        if len(step) == 4:
            name, cmd, cwd, capture = step
            env_overrides = None
        else:
            name, cmd, cwd, capture, env_overrides = step
        if not run_step(name, cmd, cwd, capture_output=capture, env_overrides=env_overrides):
            failed += 1

    if failed:
        print(f"VALIDATION SUITE RESULT: FAIL ({failed} step(s) failed)")
        return 1
    print("NOTE: Run `cmd.exe /c npm run build` in `frontend/` for full Vite bundle validation.")
    print("VALIDATION SUITE RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
