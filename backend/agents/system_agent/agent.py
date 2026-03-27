"""Main orchestrator for the system agent."""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, AsyncGenerator

from config.models import get_config
from models import ollama_client

from .executor import ToolExecutor
from .planner import TaskStep, plan_task
from .safety import AgentMode, ConfirmationRequest, check_permission


@dataclass
class AgentEvent:
    type: str
    data: dict[str, Any]


class SystemAgent:
    """Plan, execute, confirm, and summarize system tasks."""

    def __init__(self, mode: AgentMode = AgentMode.SUPERVISED) -> None:
        self.mode = mode
        self.executor = ToolExecutor()
        self._pending_confirmation: asyncio.Future[bool] | None = None

    async def run(self, task: str) -> AsyncGenerator[AgentEvent, None]:
        """Execute a task and stream structured events."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        worker = asyncio.create_task(self._run_task(task, queue))
        try:
            while True:
                event = await queue.get()
                yield event
                if event.type == "complete":
                    break
        finally:
            if not worker.done():
                worker.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await worker

    def confirm_step(self, approved: bool) -> None:
        """Resolve the current confirmation prompt."""
        if self._pending_confirmation and not self._pending_confirmation.done():
            self._pending_confirmation.set_result(bool(approved))

    async def _run_task(self, task: str, queue: asyncio.Queue[AgentEvent]) -> None:
        try:
            await self._emit(queue, "text", {"text": f"Planning task: {task}"})
            steps = await plan_task(task)
            if not steps:
                await self._emit(
                    queue,
                    "text",
                    {
                        "text": (
                            "I couldn't produce a safe step plan for that request. "
                            "Try being more explicit about the files, folders, or actions involved."
                        )
                    },
                )
                await self._emit(queue, "complete", {"success": False, "reason": "planning_failed"})
                return

            await self._emit(queue, "plan", {"steps": [asdict(step) for step in steps]})
            results: dict[int, Any] = {}

            for step in steps:
                if any(dep not in results for dep in step.depends_on):
                    await self._emit(
                        queue,
                        "step_result",
                        {
                            "step": step.step,
                            "tool": step.tool,
                            "success": False,
                            "skipped": True,
                            "reason": "Dependency not satisfied",
                        },
                    )
                    continue

                await self._emit(
                    queue,
                    "step_start",
                    {
                        "step": step.step,
                        "tool": step.tool,
                        "description": step.description,
                        "is_destructive": step.is_destructive,
                    },
                )

                try:
                    resolved_args = self._resolve_value(step.args, results)
                except Exception as exc:
                    await self._emit(
                        queue,
                        "step_error",
                        {"step": step.step, "tool": step.tool, "error": f"Argument resolution failed: {exc}"},
                    )
                    continue

                async def confirmation_callback(request: ConfirmationRequest) -> bool:
                    await self._emit(
                        queue,
                        "confirmation_needed",
                        {
                            "step": step.step,
                            "tool": step.tool,
                            "description": request.tool_call.description,
                            "risk": request.tool_call.risk.value,
                        },
                    )
                    self._pending_confirmation = asyncio.get_running_loop().create_future()
                    try:
                        return await asyncio.wait_for(self._pending_confirmation, timeout=300)
                    except asyncio.TimeoutError:
                        return False
                    finally:
                        self._pending_confirmation = None

                permitted = await check_permission(
                    step.tool,
                    resolved_args,
                    self.mode,
                    confirmation_callback=confirmation_callback,
                )
                if not permitted:
                    await self._emit(
                        queue,
                        "step_result",
                        {
                            "step": step.step,
                            "tool": step.tool,
                            "success": False,
                            "skipped": True,
                            "reason": "Denied by user or safety policy",
                        },
                    )
                    continue

                try:
                    raw_result = await self.executor.execute(step.tool, resolved_args)
                    serializable = self._jsonable(raw_result)
                    results[step.step] = serializable
                    await self._emit(
                        queue,
                        "step_result",
                        {
                            "step": step.step,
                            "tool": step.tool,
                            "success": True,
                            "result": serializable,
                        },
                    )
                except Exception as exc:
                    await self._emit(
                        queue,
                        "step_error",
                        {"step": step.step, "tool": step.tool, "error": str(exc)},
                    )

            await self._emit(queue, "text", {"text": "Synthesizing results..."})
            summary = await self._synthesize_results(task, steps, results)
            await self._emit(queue, "text", {"text": summary})
            await self._emit(
                queue,
                "complete",
                {"success": True, "steps_executed": len(results), "steps_planned": len(steps)},
            )
        except Exception as exc:
            await self._emit(queue, "text", {"text": f"System agent failed: {exc}"})
            await self._emit(queue, "complete", {"success": False, "reason": str(exc)})

    async def _emit(self, queue: asyncio.Queue[AgentEvent], event_type: str, data: dict[str, Any]) -> None:
        await queue.put(AgentEvent(type=event_type, data=data))

    def _resolve_value(self, value: Any, results: dict[int, Any]) -> Any:
        if isinstance(value, str):
            return self._resolve_reference(value, results)
        if isinstance(value, list):
            return [self._resolve_value(item, results) for item in value]
        if isinstance(value, dict):
            return {key: self._resolve_value(item, results) for key, item in value.items()}
        return value

    def _resolve_reference(self, value: str, results: dict[int, Any]) -> Any:
        match = re.fullmatch(r"\{step_(\d+)((?:\.[A-Za-z0-9_]+|\[\d+\])*)\}", value)
        if not match:
            return value
        step_num = int(match.group(1))
        current = results.get(step_num)
        path_expr = match.group(2)
        for token in re.finditer(r"\.([A-Za-z0-9_]+)|\[(\d+)\]", path_expr):
            key, index = token.groups()
            if key is not None:
                if isinstance(current, dict):
                    current = current.get(key)
                else:
                    current = getattr(current, key, None)
            elif index is not None:
                current = current[int(index)] if current is not None else None
        return current

    def _jsonable(self, value: Any) -> Any:
        if is_dataclass(value):
            return {key: self._jsonable(item) for key, item in asdict(value).items()}
        if isinstance(value, dict):
            return {str(key): self._jsonable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._jsonable(item) for item in value]
        if isinstance(value, tuple):
            return [self._jsonable(item) for item in value]
        if isinstance(value, Path):
            return str(value)
        return value

    async def _synthesize_results(
        self,
        task: str,
        steps: list[TaskStep],
        results: dict[int, Any],
    ) -> str:
        if not results:
            return "No steps completed."
        step_lookup = {step.step: step for step in steps}
        snippets = []
        for step_num, result in results.items():
            tool_name = step_lookup.get(step_num).tool if step_num in step_lookup else "unknown"
            snippets.append(f"Step {step_num} ({tool_name}): {json.dumps(result)[:800]}")
        config = get_config("chat")
        response = ""
        async for chunk in ollama_client.generate(
            model=config.model,
            prompt=(
                f"Task: {task}\n\n"
                f"Results:\n" + "\n".join(snippets) + "\n\n"
                "Provide a concise user-facing summary of what was completed, what was skipped, and any follow-up risks."
            ),
            system=config.system_prompt,
            stream=True,
            temperature=0.4,
        ):
            response += chunk
        return response
