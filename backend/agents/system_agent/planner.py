"""Task planner for the system agent."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from config.models import get_config
from models import ollama_client

AVAILABLE_TOOLS = """
FILESYSTEM TOOLS:
- filesystem.search_files(root, pattern, recursive, include_extensions, content_contains)
- filesystem.read_file(path, max_chars)
- filesystem.write_file(path, content, overwrite)
- filesystem.delete_file(path, recycle)
- filesystem.move_file(src, dst)
- filesystem.copy_file(src, dst)
- filesystem.list_directory(path)
- filesystem.get_file_hash(path)
- filesystem.create_directory(path)

SHELL TOOLS:
- shell.run_command(command, cwd, shell, timeout)
- shell.run_python_file(path, args, cwd)
- shell.run_powershell_file(path, args)

PROCESS TOOLS:
- process.list_processes(filter_name)
- process.kill_process(pid)
- process.get_system_stats()
- app_launcher.launch_application(app_name)
- app_launcher.open_path(path)

SCREEN TOOLS:
- screen.take_screenshot(monitor, save_path)
- screen.screenshot_and_analyze(question, monitor)

CLIPBOARD TOOLS:
- clipboard.read_clipboard()
- clipboard.write_clipboard(text)

BROWSER TOOLS:
- browser.open_url(url)
- browser.capture_page(url, max_images)

AI TOOLS:
- ai.analyze_file(path, question)
- ai.summarize_files(paths, style)
- ai.generate_code(description, context)
- ai.explain_error(error_text, context)
"""

PLANNER_SYSTEM = f"""You are the task planner for a local system agent.
Convert the user's request into an ordered list of atomic tool calls.

Available tools:
{AVAILABLE_TOOLS}

Rules:
- Use only the tools listed above
- Search or read before modifying files
- Use ai.analyze_file or ai.summarize_files for code/file reasoning tasks
- Use {{step_N.field}} references when a later step depends on an earlier result
- Mark destructive steps explicitly
- Maximum 20 steps
- Return ONLY JSON

JSON schema:
[
  {{
    "step": 1,
    "tool": "tool.name",
    "args": {{}},
    "description": "short human-readable description",
    "depends_on": [],
    "is_destructive": false
  }}
]"""


@dataclass
class TaskStep:
    step: int
    tool: str
    args: dict
    description: str
    depends_on: list[int]
    is_destructive: bool


async def plan_task(task: str) -> list[TaskStep]:
    """Decompose a user task into tool call steps."""
    response = ""
    config = get_config("chat")
    async for chunk in ollama_client.generate(
        model=config.model,
        prompt=f"Task: {task}",
        system=PLANNER_SYSTEM,
        stream=True,
        temperature=0.2,
        num_ctx=8192,
    ):
        response += chunk

    parsed = _parse_steps(response)
    if parsed:
        return parsed
    return _fallback_plan(task)


def _parse_steps(raw: str) -> list[TaskStep]:
    clean = raw.strip()
    fenced_match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", clean, flags=re.IGNORECASE)
    if fenced_match:
        clean = fenced_match.group(1)
    try:
        payload = json.loads(clean)
    except json.JSONDecodeError:
        return []
    steps: list[TaskStep] = []
    for item in payload:
        try:
            steps.append(
                TaskStep(
                    step=int(item["step"]),
                    tool=str(item["tool"]),
                    args=dict(item.get("args", {})),
                    description=str(item.get("description", "")),
                    depends_on=[int(value) for value in item.get("depends_on", [])],
                    is_destructive=bool(item.get("is_destructive", False)),
                )
            )
        except (KeyError, TypeError, ValueError):
            return []
    return steps


def _fallback_plan(task: str) -> list[TaskStep]:
    lowered = task.lower()
    if "screenshot" in lowered or "screen" in lowered:
        return [
            TaskStep(
                step=1,
                tool="screen.take_screenshot",
                args={"monitor": 1, "return_base64": True},
                description="Take a screenshot of the primary monitor",
                depends_on=[],
                is_destructive=False,
            )
        ]
    if "process" in lowered and any(term in lowered for term in ("list", "show", "running")):
        return [
            TaskStep(
                step=1,
                tool="process.list_processes",
                args={},
                description="List running processes",
                depends_on=[],
                is_destructive=False,
            )
        ]
    if "system stats" in lowered or "resource usage" in lowered:
        return [
            TaskStep(
                step=1,
                tool="process.get_system_stats",
                args={},
                description="Collect system resource stats",
                depends_on=[],
                is_destructive=False,
            )
        ]
    return []
