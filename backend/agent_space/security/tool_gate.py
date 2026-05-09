"""ToolGate — Policy Enforcement Point for tool calls.

Wraps every tool call with three checks, in order:

    1) capability allowlist - is this tool/agent combination permitted?
    2) arg-shape policy     - do the args match the expected schema?
    3) secret scan          - do the args contain credentials?

The gate is intentionally simpler than OPA / Cedar — those are enterprise
options the platform can graduate to later. The current goal is "make the
default secure" with zero external dependencies.

Usage::

    gate = ToolGate(default_policies)
    await gate.check(agent_id="builder", tool="run_shell", args={"command": "ls"})

Raises ``ToolGateError`` on deny.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any

from .secret_scanner import SecretScanner

logger = logging.getLogger(__name__)


class ToolGateError(RuntimeError):
    """Raised when a tool call is denied by policy."""


@dataclass
class ToolPolicy:
    tool: str
    allowed_agents: set[str] = field(default_factory=set)  # empty = all agents
    required_arg_keys: set[str] = field(default_factory=set)
    forbidden_arg_keys: set[str] = field(default_factory=set)
    max_arg_chars: int = 200_000
    rate_limit_per_minute: int = 60
    secret_scan: bool = True
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "allowed_agents": sorted(self.allowed_agents),
            "required_arg_keys": sorted(self.required_arg_keys),
            "forbidden_arg_keys": sorted(self.forbidden_arg_keys),
        }


# Default policies — match the action_type vocabulary already used by the
# Agent Space orchestrator (see backend/agent_space/orch_planning.py).
DEFAULT_POLICIES: dict[str, ToolPolicy] = {
    "read_file": ToolPolicy(tool="read_file", required_arg_keys={"path"}, max_arg_chars=4000),
    "write_file": ToolPolicy(tool="write_file", required_arg_keys={"path", "content"}, max_arg_chars=200_000),
    "replace_in_file": ToolPolicy(
        tool="replace_in_file",
        required_arg_keys={"path", "find", "replace"},
        max_arg_chars=200_000,
    ),
    "run_shell": ToolPolicy(
        tool="run_shell",
        required_arg_keys={"command"},
        max_arg_chars=8000,
        rate_limit_per_minute=30,
    ),
    "web_search": ToolPolicy(tool="web_search", required_arg_keys={"query"}, max_arg_chars=4000),
    "web_fetch": ToolPolicy(tool="web_fetch", required_arg_keys={"url"}, max_arg_chars=4000),
    "browser_open": ToolPolicy(tool="browser_open", required_arg_keys={"url"}),
    "browser_navigate": ToolPolicy(tool="browser_navigate", required_arg_keys={"url"}),
    "browser_extract": ToolPolicy(tool="browser_extract"),
    "browser_click": ToolPolicy(tool="browser_click"),
    "browser_type": ToolPolicy(tool="browser_type", max_arg_chars=8000),
    "index_search": ToolPolicy(tool="index_search", required_arg_keys={"query"}),
    "self_improve": ToolPolicy(tool="self_improve", rate_limit_per_minute=10),
    "export": ToolPolicy(tool="export"),
    "send_message": ToolPolicy(tool="send_message", max_arg_chars=20_000),
    "communicate": ToolPolicy(tool="communicate", max_arg_chars=20_000),
}


class ToolGate:
    """PEP that enforces ToolPolicy on every call before tool execution."""

    def __init__(
        self,
        *,
        policies: dict[str, ToolPolicy] | None = None,
        secret_scanner: SecretScanner | None = None,
    ) -> None:
        self.policies: dict[str, ToolPolicy] = dict(policies or DEFAULT_POLICIES)
        self.secret_scanner = secret_scanner or SecretScanner()
        # Per-(agent, tool) rate-limit deques: timestamps in last 60s.
        self._rate_window: dict[tuple[str, str], deque[float]] = {}
        self._stats = {
            "checks": 0,
            "allowed": 0,
            "denied": 0,
            "rate_limited": 0,
            "secret_blocks": 0,
        }
        self._audit: list[dict[str, Any]] = []

    def set_policy(self, policy: ToolPolicy) -> None:
        self.policies[policy.tool] = policy

    def remove_policy(self, tool: str) -> bool:
        return self.policies.pop(tool, None) is not None

    def _recent_calls(self, key: tuple[str, str]) -> deque[float]:
        if key not in self._rate_window:
            self._rate_window[key] = deque()
        return self._rate_window[key]

    def _check_rate(self, agent_id: str, tool: str, limit: int) -> bool:
        if limit <= 0:
            return True
        now = time.time()
        cutoff = now - 60.0
        window = self._recent_calls((agent_id, tool))
        while window and window[0] < cutoff:
            window.popleft()
        if len(window) >= limit:
            return False
        window.append(now)
        return True

    async def check(
        self,
        *,
        agent_id: str,
        tool: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._stats["checks"] += 1
        args = args or {}
        agent_id = str(agent_id or "").strip() or "unknown"
        tool = str(tool or "").strip()
        record: dict[str, Any] = {
            "id": uuid.uuid4().hex,
            "timestamp": time.time(),
            "agent_id": agent_id,
            "tool": tool,
            "decision": "allow",
            "reasons": [],
            "secret_findings": [],
        }
        try:
            if not tool:
                raise ToolGateError("empty tool name")

            policy = self.policies.get(tool)
            if policy is None:
                # Unknown tool — fail closed unless explicitly opted in.
                raise ToolGateError(f"no policy registered for tool '{tool}'")

            if policy.allowed_agents and agent_id not in policy.allowed_agents:
                raise ToolGateError(
                    f"agent '{agent_id}' is not in allowlist for tool '{tool}'"
                )

            for required in policy.required_arg_keys:
                if required not in args:
                    raise ToolGateError(f"tool '{tool}' missing required arg '{required}'")

            for forbidden in policy.forbidden_arg_keys:
                if forbidden in args:
                    raise ToolGateError(f"tool '{tool}' has forbidden arg '{forbidden}'")

            total_size = sum(
                len(str(v)) for v in args.values() if isinstance(v, (str, int, float))
            )
            if total_size > policy.max_arg_chars:
                raise ToolGateError(
                    f"tool '{tool}' args {total_size}b exceed max {policy.max_arg_chars}b"
                )

            if not self._check_rate(agent_id, tool, policy.rate_limit_per_minute):
                self._stats["rate_limited"] += 1
                raise ToolGateError(
                    f"tool '{tool}' rate-limited for agent '{agent_id}' "
                    f"(>{policy.rate_limit_per_minute}/min)"
                )

            if policy.secret_scan:
                findings = self.secret_scanner.scan_dict(args)
                if findings:
                    self._stats["secret_blocks"] += 1
                    record["secret_findings"] = [f.to_dict() for f in findings]
                    raise ToolGateError(
                        f"tool '{tool}' arg contains {len(findings)} secret(s); "
                        f"first: {findings[0].rule}"
                    )

            self._stats["allowed"] += 1
            record["decision"] = "allow"
            return record

        except ToolGateError as exc:
            self._stats["denied"] += 1
            record["decision"] = "deny"
            record["reasons"].append(str(exc))
            logger.warning(
                "ToolGate DENY tool=%s agent=%s reason=%s",
                tool, agent_id, exc,
            )
            raise
        finally:
            self._audit.append(record)
            if len(self._audit) > 5000:
                self._audit = self._audit[-2500:]

    def list_policies(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self.policies.values()]

    def recent_audit(self, *, limit: int = 200) -> list[dict[str, Any]]:
        return list(self._audit[-max(1, int(limit)):])

    def stats(self) -> dict[str, Any]:
        return {**self._stats, "policy_count": len(self.policies)}
