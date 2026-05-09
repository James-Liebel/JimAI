"""Lazy singletons for the security agents.

Construction is cheap; we still memoize so the rest of the platform can
import these without holding state. Each singleton is configurable via
its constructor; runtime config plumbing is left to api/security_api.py.
"""

from __future__ import annotations

import logging

from .behavior_monitor import BehaviorMonitor
from .egress_guardian import EgressGuardian
from .prompt_shield import PromptShield
from .secret_scanner import SecretScanner
from .supply_chain_sentinel import SupplyChainSentinel
from .tool_gate import DEFAULT_POLICIES, ToolGate

logger = logging.getLogger(__name__)


_prompt_shield: PromptShield | None = None
_secret_scanner: SecretScanner | None = None
_tool_gate: ToolGate | None = None
_egress_guardian: EgressGuardian | None = None
_behavior_monitor: BehaviorMonitor | None = None
_supply_chain_sentinel: SupplyChainSentinel | None = None


def get_prompt_shield() -> PromptShield:
    global _prompt_shield
    if _prompt_shield is None:
        _prompt_shield = PromptShield()
    return _prompt_shield


def get_secret_scanner() -> SecretScanner:
    global _secret_scanner
    if _secret_scanner is None:
        _secret_scanner = SecretScanner()
    return _secret_scanner


def get_tool_gate() -> ToolGate:
    global _tool_gate
    if _tool_gate is None:
        _tool_gate = ToolGate(
            policies=dict(DEFAULT_POLICIES),
            secret_scanner=get_secret_scanner(),
        )
    return _tool_gate


def get_egress_guardian() -> EgressGuardian:
    global _egress_guardian
    if _egress_guardian is None:
        _egress_guardian = EgressGuardian()
    return _egress_guardian


def get_behavior_monitor() -> BehaviorMonitor:
    global _behavior_monitor
    if _behavior_monitor is None:
        _behavior_monitor = BehaviorMonitor()
    return _behavior_monitor


def get_supply_chain_sentinel() -> SupplyChainSentinel:
    global _supply_chain_sentinel
    if _supply_chain_sentinel is None:
        _supply_chain_sentinel = SupplyChainSentinel()
    return _supply_chain_sentinel


def all_stats() -> dict[str, dict]:
    """Aggregate stats for the dashboard."""
    return {
        "prompt_shield": get_prompt_shield().stats(),
        "secret_scanner": get_secret_scanner().stats(),
        "tool_gate": get_tool_gate().stats(),
        "egress_guardian": get_egress_guardian().stats(),
        "behavior_monitor": get_behavior_monitor().stats(),
        "supply_chain_sentinel": get_supply_chain_sentinel().stats(),
    }
