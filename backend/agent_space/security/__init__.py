"""Defensive cybersecurity agents for Agent Space.

Six lightweight, locally-runnable defensive agents — each independently
useful, designed to compose:

    * prompt_shield        - block prompt injection in user / RAG input
    * secret_scanner       - block secret leakage in tool args / outputs
    * tool_gate            - capability allowlist + arg-shape policy for tool calls
    * egress_guardian      - PII scrub + domain allowlist on outbound traffic
    * behavior_monitor     - heuristic agent-loop watchdog (cap, dedup, n-gram)
    * supply_chain_sentinel - CVE scan against pip / npm dependencies

All run fully local. Heavier model-backed checks (Granite Guardian, Llama
Guard) are optional and pluggable via ``prompt_shield.use_guardrail_model``.
"""

from .prompt_shield import PromptShield, ShieldVerdict
from .secret_scanner import SecretScanner, SecretFinding
from .tool_gate import ToolGate, ToolGateError, ToolPolicy
from .egress_guardian import EgressGuardian, EgressVerdict
from .behavior_monitor import BehaviorMonitor, BehaviorViolation, RunGuard
from .supply_chain_sentinel import SupplyChainSentinel, CveFinding

__all__ = [
    "PromptShield",
    "ShieldVerdict",
    "SecretScanner",
    "SecretFinding",
    "ToolGate",
    "ToolGateError",
    "ToolPolicy",
    "EgressGuardian",
    "EgressVerdict",
    "BehaviorMonitor",
    "BehaviorViolation",
    "RunGuard",
    "SupplyChainSentinel",
    "CveFinding",
]
