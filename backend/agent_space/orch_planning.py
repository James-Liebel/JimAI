"""Agent Space orchestrator — planning and action-selection helpers.

Pure functions extracted from AgentSpaceOrchestrator for modularity.
All functions are side-effect-free and operate only on plain Python types.
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Research query builders
# ---------------------------------------------------------------------------

def _research_query_from_objective(objective: str) -> str:
    text = re.sub(r"\s+", " ", str(objective or "").strip())
    if not text:
        return "software product market research best practices"
    if len(text) > 160:
        text = text[:160]
    return f"{text} market competitors business model"


def _research_query_variants(objective: str, min_queries: int) -> list[str]:
    base = re.sub(r"\s+", " ", str(objective or "").strip())
    if not base:
        base = "software app"
    if len(base) > 140:
        base = base[:140]
    queries = [
        f"{base} market competitors business model",
        f"{base} best UX patterns and onboarding",
        f"{base} monetization pricing examples",
        f"{base} feature benchmarks and user pain points",
        f"{base} architecture and implementation constraints",
    ]
    cleaned: list[str] = []
    for q in queries:
        value = q.strip()
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned[: max(1, min_queries)]


# ---------------------------------------------------------------------------
# Action classification helpers
# ---------------------------------------------------------------------------

def _is_research_action(action: dict[str, Any]) -> bool:
    action_type = str(action.get("type", "")).strip()
    return action_type in {
        "web_search",
        "web_fetch",
        "browser_open",
        "browser_navigate",
        "browser_extract",
        "browser_links",
        "browser_state",
    }


def _is_recoverable_action_type(action_type: str) -> bool:
    return action_type in {
        "run_shell",
        "web_search",
        "web_fetch",
        "browser_open",
        "browser_navigate",
        "browser_extract",
        "browser_links",
        "browser_state",
        "browser_click",
        "browser_type",
        "browser_screenshot",
        "browser_cursor_move",
        "browser_cursor_click",
        "browser_cursor_hover",
        "browser_scroll",
        "browser_cursor_scroll",
        "browser_close",
        "browser_close_all",
    }


# ---------------------------------------------------------------------------
# Objective classification helpers
# ---------------------------------------------------------------------------

def _is_deterministic_file_objective(objective: str) -> bool:
    text = str(objective or "").strip()
    if not text:
        return False
    patterns = (
        r"^create file\s+\S+\s+with\s+.+$",
        r"^write\s+.+\s+to\s+\S+$",
        r"^replace\s+'[^']+'\s+with\s+'[^']+'\s+in\s+\S+$",
    )
    return any(re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) for pattern in patterns)


def _objective_needs_research(objective: str) -> bool:
    text = str(objective or "").strip().lower()
    if not text:
        return False
    if _is_deterministic_file_objective(objective):
        return False
    research_signals = (
        "current",
        "latest",
        "recent",
        "today",
        "right now",
        "live",
        "real-time",
        "pricing",
        "price",
        "cost",
        "market",
        "competitor",
        "competition",
        "benchmark",
        "trend",
        "research",
        "browse",
        "look up",
        "search web",
    )
    return any(signal in text for signal in research_signals)
