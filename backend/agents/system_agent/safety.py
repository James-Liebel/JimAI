"""Safety and confirmation policy for the system agent."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable

from .tools import shell as shell_tools


class AgentMode(str, Enum):
    SUPERVISED = "supervised"
    AUTONOMOUS = "autonomous"


class RiskLevel(str, Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DESTRUCTIVE = "destructive"


@dataclass
class ToolCall:
    tool: str
    args: dict
    risk: RiskLevel
    description: str


@dataclass
class ConfirmationRequest:
    tool_call: ToolCall
    requires_response: bool
    auto_approve_in: int | None


def classify_risk(tool: str, args: dict) -> RiskLevel:
    """Classify a tool call by potential impact."""
    tool_lower = tool.lower()

    safe_terms = (
        "analyze",
        "get",
        "list",
        "read",
        "search",
        "screenshot",
        "stats",
    )
    if any(term in tool_lower for term in safe_terms) and "write_clipboard" not in tool_lower:
        return RiskLevel.SAFE

    destructive_terms = ("delete", "kill", "permanent")
    if any(term in tool_lower for term in destructive_terms):
        return RiskLevel.DESTRUCTIVE

    if "shell" in tool_lower or "run_command" in tool_lower:
        if shell_tools.requires_confirmation(str(args.get("command", ""))):
            return RiskLevel.DESTRUCTIVE
        return RiskLevel.CAUTION

    if any(term in tool_lower for term in ("write", "move", "copy", "open_application", "launch")):
        return RiskLevel.DESTRUCTIVE if bool(args.get("overwrite")) else RiskLevel.CAUTION

    if "clipboard.write" in tool_lower:
        return RiskLevel.CAUTION

    return RiskLevel.CAUTION


async def check_permission(
    tool: str,
    args: dict,
    mode: AgentMode,
    confirmation_callback: Callable[[ConfirmationRequest], Awaitable[bool]] | None = None,
) -> bool:
    """Return True when the tool call is permitted to proceed."""
    risk = classify_risk(tool, args)
    if risk == RiskLevel.SAFE:
        return True
    if risk == RiskLevel.CAUTION and mode == AgentMode.AUTONOMOUS:
        return True

    request = ConfirmationRequest(
        tool_call=ToolCall(
            tool=tool,
            args=args,
            risk=risk,
            description=_describe_tool_call(tool, args),
        ),
        requires_response=True,
        auto_approve_in=None,
    )
    if confirmation_callback is None:
        return False
    return await confirmation_callback(request)


def _describe_tool_call(tool: str, args: dict) -> str:
    descriptions = {
        "filesystem.write_file": lambda value: f"Write to {value.get('path', '?')} ({len(value.get('content', ''))} chars)",
        "filesystem.delete_file": lambda value: (
            f"{'Permanently delete' if not value.get('recycle', True) else 'Send to Recycle Bin'} {value.get('path', '?')}"
        ),
        "filesystem.move_file": lambda value: f"Move {value.get('src', '?')} -> {value.get('dst', '?')}",
        "filesystem.copy_file": lambda value: f"Copy {value.get('src', '?')} -> {value.get('dst', '?')}",
        "shell.run_command": lambda value: f"Run command: {str(value.get('command', '?'))[:120]}",
        "process.kill_process": lambda value: f"Kill process PID {value.get('pid', '?')}",
        "clipboard.write_clipboard": lambda value: f"Write {len(value.get('text', ''))} chars to the clipboard",
        "app_launcher.open_path": lambda value: f"Open {value.get('path', '?')}",
        "app_launcher.launch_application": lambda value: f"Launch application {value.get('app_name', '?')}",
    }
    describe = descriptions.get(tool)
    if describe is not None:
        return describe(args)
    preview = ", ".join(f"{key}={value}" for key, value in list(args.items())[:3])
    return f"{tool}({preview})"
