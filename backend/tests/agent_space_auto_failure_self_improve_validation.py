"""Validation script for automatic failure-triggered self-improvement recovery."""

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
    original_run_self_improve = runtime.proactive_engine.run_self_improvement
    original_settings = runtime.settings_store.get()
    original_auto_state = dict(runtime.proactive_engine._auto_failure_state)

    captured_recovery_calls: list[dict[str, Any]] = []

    async def fake_execute_subagent(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        agent_id = str(kwargs.get("agent_id") or "")
        spec = dict(kwargs.get("spec") or {})
        role = str(spec.get("role") or "")
        if agent_id == "failer":
            raise RuntimeError("intentional failer error for auto-recovery validation")
        if role == "verifier":
            return {"accepted": True, "summary": "verification passed"}
        return {"success": True, "summary": f"{agent_id} completed"}

    async def fake_run_self_improvement(
        self,
        *,
        prompt: str,
        confirmed_suggestions: list[str],
        auto_recovery: bool = False,
        parent_run_id: str = "",
    ) -> dict[str, Any]:
        captured_recovery_calls.append(
            {
                "prompt": prompt,
                "confirmed_suggestions": list(confirmed_suggestions),
                "auto_recovery": auto_recovery,
                "parent_run_id": parent_run_id,
            }
        )
        return {"id": f"auto-self-{len(captured_recovery_calls)}"}

    runtime.orchestrator._execute_subagent = types.MethodType(fake_execute_subagent, runtime.orchestrator)  # type: ignore[assignment]
    runtime.proactive_engine.run_self_improvement = types.MethodType(fake_run_self_improvement, runtime.proactive_engine)  # type: ignore[assignment]

    runtime.settings_store.update(
        {
            "auto_self_improve_on_failure_enabled": True,
            "auto_self_improve_on_failure_include_stopped": False,
            "auto_self_improve_on_failure_cooldown_seconds": 0,
            "auto_self_improve_on_failure_max_per_day": 10,
        }
    )
    runtime.proactive_engine._auto_failure_state = runtime.proactive_engine._default_auto_failure_state()
    runtime.proactive_engine._save_auto_failure_state()

    try:
        await runtime.power_manager.set_state(True, release_gpu_on_off=False)

        run = await runtime.orchestrator.start_run(
            {
                "objective": "Validate automatic failure self-improvement trigger",
                "autonomous": False,
                "review_gate": False,
                "allow_shell": False,
                "strict_verification": False,
                "continue_on_subagent_failure": False,
                "subagent_retry_attempts": 0,
                "subagents": [
                    {"id": "planner", "role": "planner", "depends_on": []},
                    {"id": "failer", "role": "coder", "depends_on": ["planner"], "actions": []},
                ],
            }
        )
        run_id = str(run["id"])
        final = await wait_for_terminal(run_id, timeout_seconds=30.0)
        events = list(final.get("events") or [])
        event_types = [str(evt.get("type")) for evt in events]

        print("AUTO RECOVERY RUN:", {"id": run_id, "status": final.get("status")})
        print(
            "AUTO RECOVERY EVENTS:",
            {
                "run_failed": "run.failed" in event_types,
                "run_auto_recovery": "run.auto_recovery" in event_types,
            },
        )
        print("AUTO RECOVERY QUEUES:", {"count": len(captured_recovery_calls)})

        assert final.get("status") == "failed"
        assert "run.failed" in event_types
        assert "run.auto_recovery" in event_types
        assert len(captured_recovery_calls) == 1
        assert bool(captured_recovery_calls[0].get("auto_recovery")) is True
        assert str(captured_recovery_calls[0].get("parent_run_id")) == run_id

        flagged = await runtime.orchestrator.start_run(
            {
                "objective": "Validate auto-recovery skip flag",
                "autonomous": False,
                "review_gate": False,
                "allow_shell": False,
                "strict_verification": False,
                "continue_on_subagent_failure": False,
                "subagent_retry_attempts": 0,
                "auto_failure_self_improve_run": True,
                "skip_auto_failure_self_improve": True,
                "subagents": [
                    {"id": "planner", "role": "planner", "depends_on": []},
                    {"id": "failer", "role": "coder", "depends_on": ["planner"], "actions": []},
                ],
            }
        )
        flagged_final = await wait_for_terminal(str(flagged["id"]), timeout_seconds=30.0)
        assert flagged_final.get("status") == "failed"
        assert len(captured_recovery_calls) == 1

        print("AUTO FAILURE SELF-IMPROVE VALIDATION RESULT: PASS")
    finally:
        runtime.orchestrator._execute_subagent = original_execute  # type: ignore[assignment]
        runtime.proactive_engine.run_self_improvement = original_run_self_improve  # type: ignore[assignment]
        runtime.settings_store.update(original_settings)
        runtime.proactive_engine._auto_failure_state = original_auto_state
        runtime.proactive_engine._save_auto_failure_state()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
