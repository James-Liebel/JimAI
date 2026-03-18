"""Agent Space orchestrator — general static utility helpers.

Pure functions extracted from AgentSpaceOrchestrator for modularity.
All functions are side-effect-free and operate only on plain Python types.
"""

from __future__ import annotations

from typing import Any

from .paths import DATA_ROOT, PROJECT_ROOT


# ---------------------------------------------------------------------------
# Role helpers
# ---------------------------------------------------------------------------

def _sanitize_role(role: str) -> str:
    value = role.strip().lower()
    if not value:
        return "coder"
    compact = value.replace("-", " ").replace("_", " ")
    if "plan" in compact:
        return "planner"
    if "verif" in compact or "validat" in compact or "audit" in compact:
        return "verifier"
    if "test" in compact or compact == "qa":
        return "tester"
    if "security" in compact:
        return "tester"
    if "engineer" in compact or "developer" in compact or "coder" in compact:
        return "coder"
    aliases = {
        "developer": "coder",
        "engineer": "coder",
        "qa": "tester",
        "reviewer": "verifier",
        "validator": "verifier",
    }
    return aliases.get(value, value)


# ---------------------------------------------------------------------------
# ID / list helpers
# ---------------------------------------------------------------------------

def _with_unique_id(existing: set[str], preferred: str, fallback_prefix: str) -> str:
    base = preferred.strip() or fallback_prefix
    candidate = base
    n = 2
    while candidate in existing:
        candidate = f"{base}-{n}"
        n += 1
    existing.add(candidate)
    return candidate


def _dedupe_list(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        v = str(value or "").strip()
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


# ---------------------------------------------------------------------------
# Worker scope / action selection
# ---------------------------------------------------------------------------

def _worker_scope_line(role: str, worker_level: int, complexity_level: str) -> str:
    if role == "planner":
        return "Create a structured plan and handoffs before any implementation."
    if role == "verifier":
        return "Verify other worker outputs, surface gaps, and issue final pass/fail guidance."
    if role == "tester":
        if worker_level >= 3:
            return "Run deep validation, edge-case checks, and release-readiness verification."
        if worker_level == 2:
            return "Run integration and behavioral checks across updated modules."
        return "Run core sanity checks for implemented changes."
    if worker_level >= 3:
        return f"Handle high-complexity hardening tasks for {complexity_level}-complexity work."
    if worker_level == 2:
        return f"Handle integration-level implementation tasks for {complexity_level}-complexity work."
    return f"Handle focused implementation tasks for {complexity_level}-complexity work."


def _select_actions_for_worker(
    actions: list[dict[str, Any]],
    *,
    complexity_level: str,
    worker_level: int,
) -> list[dict[str, Any]]:
    normalized_actions = [a for a in actions if isinstance(a, dict)]
    if not normalized_actions:
        return []
    level = max(1, int(worker_level))
    complexity = str(complexity_level or "low")
    if complexity == "low":
        return list(normalized_actions)

    heavy = {"run_shell", "export", "self_improve"}
    if complexity == "medium":
        if level <= 1:
            selected = [a for a in normalized_actions if str(a.get("type")) not in heavy]
            return selected or list(normalized_actions)
        selected = [a for a in normalized_actions if str(a.get("type")) in heavy]
        return selected or list(normalized_actions)

    l1_types = {
        "read_file",
        "index_search",
        "web_search",
        "web_fetch",
        "read_messages",
        "browser_open",
        "browser_navigate",
        "browser_extract",
        "browser_state",
        "browser_links",
    }
    l2_types = {
        "write_file",
        "replace_in_file",
        "browser_click",
        "browser_type",
        "browser_screenshot",
        "browser_cursor_move",
        "browser_cursor_click",
        "browser_cursor_hover",
        "browser_scroll",
        "browser_cursor_scroll",
    }
    l3_types = heavy.union({"send_message", "communicate"})
    bucket = l1_types if level <= 1 else (l2_types if level == 2 else l3_types)
    selected = [a for a in normalized_actions if str(a.get("type")) in bucket]
    return selected or list(normalized_actions)


# ---------------------------------------------------------------------------
# Text / code helpers
# ---------------------------------------------------------------------------

def _strip_code_fence(text: str) -> str:
    raw = str(text or "").strip()
    if raw.startswith("```") and raw.endswith("```"):
        body = raw[3:-3].strip()
        lines = body.splitlines()
        if lines and not lines[0].strip().startswith(("{", "[", "<")) and len(lines[0].strip()) <= 20:
            return "\n".join(lines[1:]).strip()
        return body
    return raw


# ---------------------------------------------------------------------------
# Self-improve path helpers
# ---------------------------------------------------------------------------

def _extract_self_improve_paths(changes: dict[str, dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for row in list(changes.values()):
        reason = str(row.get("reason", ""))
        if reason not in {"self_improve", "self_improve_code"}:
            continue
        path = str(row.get("path", "")).strip()
        if path and path not in paths:
            paths.append(path)
    return paths


def _default_self_improve_report_path() -> str:
    try:
        return (DATA_ROOT / "self_improvement" / "latest.md").resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except Exception:
        return "data/agent_space/self_improvement/latest.md"


# ---------------------------------------------------------------------------
# Path permission helper
# ---------------------------------------------------------------------------

def _is_path_allowed(rel_path: str, allowed_paths: list[str]) -> bool:
    rel = rel_path.strip("/")
    for allowed in allowed_paths:
        scope = allowed.strip("/")
        if not scope:
            return True
        if rel == scope or rel.startswith(f"{scope}/"):
            return True
    return False
