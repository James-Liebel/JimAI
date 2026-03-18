"""Validation script for continue_on_subagent_failure using orchestrator runtime directly."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import types
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agent_space import runtime


async def wait_for_terminal(run_id: str, timeout_seconds: float = 30.0) -> dict[str, Any]:
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        row = runtime.orchestrator.get_run(run_id)
        if isinstance(row, dict):
            status = str(row.get("status") or "")
            if status in {"completed", "failed", "stopped"}:
                return row
        await asyncio.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for run {run_id}")


async def main_async() -> None:
    original_execute = runtime.orchestrator._execute_subagent

    async def fake_execute_subagent(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        agent_id = str(kwargs.get("agent_id") or "")
        spec = dict(kwargs.get("spec") or {})
        role = str(spec.get("role") or "")
        if agent_id == "failer":
            raise RuntimeError("intentional failer error for validation")
        if role == "verifier":
            return {"accepted": True, "summary": "verification passed"}
        return {"success": True, "summary": f"{agent_id} completed"}

    runtime.orchestrator._execute_subagent = types.MethodType(fake_execute_subagent, runtime.orchestrator)  # type: ignore[assignment]

    try:
        await runtime.power_manager.set_state(True, release_gpu_on_off=False)

        run = await runtime.orchestrator.start_run(
            {
                "objective": "Validate continue-on-subagent-failure behavior",
                "autonomous": False,
                "review_gate": False,
                "allow_shell": False,
                "strict_verification": False,
                "continue_on_subagent_failure": True,
                "subagent_retry_attempts": 0,
                "subagents": [
                    {"id": "planner", "role": "planner", "depends_on": []},
                    {"id": "failer", "role": "coder", "depends_on": ["planner"], "actions": []},
                    {"id": "finisher", "role": "coder", "depends_on": ["failer"], "actions": []},
                    {"id": "verifier", "role": "verifier", "depends_on": ["finisher"]},
                ],
            }
        )
        run_id = str(run["id"])
        final = await wait_for_terminal(run_id, timeout_seconds=30.0)
        events = list(final.get("events") or [])
        event_types = [str(evt.get("type")) for evt in events]

        print("CONTINUE FAILURE RUN:", {"id": run_id, "status": final.get("status")})
        print(
            "CONTINUE FAILURE EVENTS:",
            {
                "subagent_error": "subagent.error" in event_types,
                "subagent_continued": "subagent.continued" in event_types,
                "run_completed": "run.completed" in event_types,
            },
        )

        assert final.get("status") == "completed"
        assert "subagent.error" in event_types
        assert "subagent.continued" in event_types
        assert "run.completed" in event_types
        print("CONTINUE ON FAILURE VALIDATION RESULT: PASS")
    finally:
        runtime.orchestrator._execute_subagent = original_execute  # type: ignore[assignment]


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
