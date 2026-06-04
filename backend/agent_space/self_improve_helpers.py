"""Self-improve suggestion pipeline helpers.

Extracted verbatim from ``api.py``: candidate generation, the critic pruning
pass, codebase-signal assembly, and prompt strengthening. The route handlers in
``api.py`` import these back, so behaviour is unchanged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncGenerator

from fastapi import Request

from models import ollama_client
from config.role_prompts import (
    SELF_IMPROVE_GENERATOR,
    SELF_IMPROVE_CRITIC,
    SELF_IMPROVE_STRENGTHEN,
)
from . import knowledge_store
from .paths import PROJECT_ROOT
from .runtime import log_store, settings_store

logger = logging.getLogger(__name__)


def _safe_parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        loaded = json.loads(text)
        if isinstance(loaded, dict):
            return loaded
    except (json.JSONDecodeError, ValueError):
        logger.warning("_safe_parse_json_object: initial JSON parse failed, trying regex extraction", exc_info=True)
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        loaded = json.loads(match.group(0))
        if isinstance(loaded, dict):
            return loaded
    except (json.JSONDecodeError, ValueError):
        return None
    return None


def _normalize_suggestion_texts(items: list[str], *, max_items: int) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = " ".join(str(item or "").strip().split())
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
        if len(cleaned) >= max(1, max_items):
            break
    return cleaned


_TARGET_SIGNAL_TOKENS = (
    "frontend/", "backend/", "page", "endpoint", "workflow", "review",
    "builder", "self-code", "settings", "metric", "event", "summary", "retry",
)


def _specificify_suggestions(items: list[str], prompt: str, *, max_items: int) -> list[str]:
    """Normalize, dedup, and ensure each suggestion has a concrete target.

    Suggestions that already mention a file path / known UI surface are left
    alone; vague ones get a trailing 'Target: ... Expected result: ...' hint
    derived from the original user prompt so the downstream coder has scope.
    """
    prompt_hint = " ".join(str(prompt or "").strip().split())[:90]
    out: list[str] = []
    for item in items:
        cleaned = " ".join(str(item or "").strip().split())
        if not cleaned:
            continue
        lower = cleaned.lower()
        if any(tok in lower for tok in _TARGET_SIGNAL_TOKENS) and len(cleaned.split()) >= 8:
            out.append(cleaned)
        else:
            out.append(
                f"{cleaned} Target: Improve this scope -> {prompt_hint}. "
                "Expected result: measurable reliability or UX gain."
            )
    return _normalize_suggestion_texts(out, max_items=max_items)


def _fallback_self_improve_suggestions(prompt: str, focus: str, *, max_items: int) -> list[str]:
    prompt_hint = str(prompt or "").strip()
    base = [
        (
            "Improve `frontend/src/pages/SelfCode.tsx` so users can run prompt-direct or "
            "suggestion-confirmed flows with clear disabled states and completion feedback."
        ),
        (
            "Improve `backend/agent_space/orchestrator.py` action resilience by retrying failed "
            "recoverable actions and applying fallback methods before marking failure."
        ),
        (
            "Add automatic run-completion summaries that include status, action count, "
            "review/snapshot outputs, and confirmed self-improve goals."
        ),
        (
            "Improve planner and verifier handoff quality by requiring specific follow-up messages "
            "with actionable checks for unresolved risks."
        ),
        (
            f"Prioritize self-learning focus `{focus}` with concrete file/endpoint targets "
            "and acceptance checks in each proposal."
        ),
        (
            f"Strengthen build reliability for this request scope: {prompt_hint}. "
            "Target result: fewer failed runs and faster autonomous completion."
        ),
    ]
    return _specificify_suggestions(base, prompt_hint, max_items=max_items)


def _build_codebase_signal(max_chars: int = 2400) -> str:
    """Compact, model-friendly summary of *current* codebase pain points.

    Three sections, each capped to keep the payload short:
      1. Run metrics — actions/runs failure rates from the LogStore.
      2. Recent issues — last 15 entries from issues.jsonl with source+type+message.
      3. Heaviest files — top files by line count under backend/agent_space,
         backend/api, frontend/src/pages so the model knows where complexity sits.

    Returns "" if nothing meaningful is available (fresh checkout, no logs).
    """
    lines: list[str] = []
    try:
        metrics = log_store.get_metrics()
        if metrics:
            failed_actions = int(metrics.get("actions_failed", 0))
            total_actions = int(metrics.get("actions_total", 0))
            fail_pct = (100.0 * failed_actions / total_actions) if total_actions else 0.0
            lines.append(
                "Run metrics: "
                f"runs_started={metrics.get('runs_started', 0)} "
                f"completed={metrics.get('runs_completed', 0)} "
                f"failed={metrics.get('runs_failed', 0)} "
                f"actions_failed={failed_actions}/{total_actions} ({fail_pct:.1f}%) "
                f"rollbacks={metrics.get('rollbacks', 0)}"
            )
    except Exception:
        pass

    try:
        issues = log_store.list_issues(60)[-15:]
        if issues:
            lines.append("Recent issues (newest last):")
            for entry in issues:
                src = str(entry.get("source", ""))[:24]
                kind = str(entry.get("type", ""))[:32]
                msg = " ".join(str(entry.get("message", "")).split())[:120]
                lines.append(f"  - [{src}/{kind}] {msg}")
    except Exception:
        pass

    try:
        targets = [
            PROJECT_ROOT / "backend" / "agent_space",
            PROJECT_ROOT / "backend" / "api",
            PROJECT_ROOT / "frontend" / "src" / "pages",
        ]
        sized: list[tuple[int, str]] = []
        for root in targets:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                suffix = path.suffix.lower()
                if suffix not in {".py", ".ts", ".tsx"}:
                    continue
                try:
                    n_lines = sum(1 for _ in path.open("r", encoding="utf-8", errors="ignore"))
                except Exception:
                    continue
                rel = path.relative_to(PROJECT_ROOT).as_posix()
                sized.append((n_lines, rel))
        sized.sort(reverse=True)
        top = sized[:12]
        if top:
            lines.append("Heaviest source files (lines):")
            for n_lines, rel in top:
                lines.append(f"  - {rel} ({n_lines} lines)")
    except Exception:
        pass

    if not lines:
        return ""
    blob = "\n".join(lines)
    if len(blob) > max_chars:
        blob = blob[: max_chars - 3] + "..."
    return blob


def _generator_user_prompt(
    prompt: str,
    focus: str,
    max_suggestions: int,
    signal: str = "",
) -> str:
    parts = [
        f"User improvement prompt:\n{prompt.strip()}",
        f"Current self-learning focus: {focus}",
    ]
    if signal:
        parts.append(
            "Current codebase signal (use this to anchor concrete proposals — "
            "prefer files/issues that appear here over generic ideas):\n" + signal
        )
    knowledge = knowledge_store.knowledge_prompt_block()
    if knowledge:
        parts.append(knowledge)
    parts.append(
        f"Generate 8–{max(8, max_suggestions + 2)} candidates per the schema in your system prompt. "
        "Every candidate must name at least one file in scope_files; prefer files appearing in the "
        "codebase signal above. If you propose a fix for a listed issue, mention the issue type in rationale."
    )
    return "\n\n".join(parts)


def _critic_user_prompt(candidates_json: str, max_suggestions: int) -> str:
    return (
        f"Score and rank these candidates per the schema in your system prompt. "
        f"Keep at most {max_suggestions} candidates with verdict='keep'.\n\n"
        f"Candidates:\n{candidates_json}"
    )


async def _critic_prune(
    raw_candidates: list[dict[str, Any]],
    model: str,
    max_suggestions: int,
) -> list[dict[str, Any]]:
    """Second pass: same model, lower temperature, scores and prunes candidates.

    Returns ranked entries (verdict=='keep') ordered best-first. On failure,
    falls back to the input order truncated to max_suggestions.
    """
    if not raw_candidates:
        return []
    try:
        text = await ollama_client.chat_full(
            model=model,
            messages=[
                {"role": "system", "content": SELF_IMPROVE_CRITIC},
                {"role": "user", "content": _critic_user_prompt(
                    json.dumps({"candidates": raw_candidates}, ensure_ascii=False),
                    max_suggestions,
                )},
            ],
            temperature=0.05,
        )
        parsed = _safe_parse_json_object(text) or {}
        ranked = parsed.get("ranked") if isinstance(parsed, dict) else []
        if not isinstance(ranked, list):
            ranked = []
        kept = [r for r in ranked if isinstance(r, dict) and str(r.get("verdict")) == "keep"]
        kept.sort(key=lambda r: int(r.get("overall") or 0), reverse=True)
        return kept[:max_suggestions]
    except Exception:
        return raw_candidates[:max_suggestions]


def _candidates_to_strings(candidates: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for c in candidates:
        title = str(c.get("title") or "").strip()
        if not title:
            continue
        scope = c.get("scope_files") or []
        scope_str = ", ".join(str(s) for s in scope if s) if isinstance(scope, list) else ""
        acceptance = str(c.get("acceptance") or "").strip()
        bits = [title]
        if scope_str:
            bits.append(f"Scope: {scope_str}.")
        if acceptance:
            bits.append(f"Done when: {acceptance}.")
        out.append(" ".join(bits))
    return out


async def _generate_self_improve_suggestions(prompt: str, max_suggestions: int) -> dict[str, Any]:
    settings = settings_store.get()
    model = str(settings.get("model", "qwen2.5-coder:14b"))
    focus = str(settings.get("self_learning_focus", "general"))
    fallback = _fallback_self_improve_suggestions(prompt, focus, max_items=max_suggestions)
    suggestions = list(fallback)
    autonomous_notes: list[str] = []

    signal = _build_codebase_signal()
    try:
        gen_text = await ollama_client.chat_full(
            model=model,
            messages=[
                {"role": "system", "content": SELF_IMPROVE_GENERATOR},
                {"role": "user", "content": _generator_user_prompt(prompt, focus, max_suggestions, signal)},
            ],
            temperature=0.4,
        )
        parsed = _safe_parse_json_object(gen_text) or {}
        candidates = parsed.get("candidates") if isinstance(parsed, dict) else []
        if not isinstance(candidates, list):
            candidates = []

        ranked = await _critic_prune(candidates, model, max_suggestions)
        kept_strings = _candidates_to_strings(ranked)
        if kept_strings:
            suggestions = _specificify_suggestions(kept_strings, prompt, max_items=max_suggestions)
        else:
            suggestions = fallback
        autonomous_notes = [
            f"critic verdict: {len(ranked)} kept of {len(candidates)} generated"
        ] if candidates else []
    except Exception:
        suggestions = fallback
        autonomous_notes = []

    return {
        "model": model,
        "focus": focus,
        "suggestions": suggestions,
        "autonomous_notes": autonomous_notes,
    }


async def _stream_self_improve_suggestions(
    prompt: str,
    max_suggestions: int,
    request: Request,
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream NDJSON events for suggest: meta, action, chunk, progress, then result (or stopped)."""
    settings = settings_store.get()
    model = str(settings.get("model", "qwen2.5-coder:14b"))
    focus = str(settings.get("self_learning_focus", "general"))
    fallback = _fallback_self_improve_suggestions(prompt, focus, max_items=max_suggestions)
    yield {"type": "meta", "model": model, "focus": focus}
    yield {"type": "action", "stage": "ollama", "label": "Calling local model (streaming)…"}

    signal = _build_codebase_signal()
    if signal:
        yield {
            "type": "action",
            "stage": "signal",
            "label": f"Loaded codebase signal · {signal.count(chr(10)) + 1} lines",
        }
    llm_prompt = _generator_user_prompt(prompt, focus, max_suggestions, signal)
    parts: list[str] = []
    progress_mark = 0
    try:
        async for piece in ollama_client.chat_stream(
            model=model,
            messages=[
                {"role": "system", "content": SELF_IMPROVE_GENERATOR},
                {"role": "user", "content": llm_prompt},
            ],
            temperature=0.4,
        ):
            parts.append(piece)
            yield {"type": "chunk", "text": piece}
            total_chars = sum(len(p) for p in parts)
            if total_chars - progress_mark >= 4096:
                progress_mark = total_chars
                yield {"type": "progress", "chars": total_chars}
            if await request.is_disconnected():
                yield {"type": "stopped", "reason": "client_disconnected", "partial_chars": total_chars}
                return
    except asyncio.CancelledError:
        yield {
            "type": "stopped",
            "reason": "cancelled",
            "partial_chars": sum(len(p) for p in parts),
        }
        raise

    yield {"type": "action", "stage": "parse", "label": "Parsing JSON response…"}
    text = "".join(parts)
    suggestions = list(fallback)
    autonomous_notes: list[str] = []
    try:
        parsed = _safe_parse_json_object(text) or {}
        candidates = parsed.get("candidates") if isinstance(parsed, dict) else []
        if not isinstance(candidates, list):
            candidates = []

        yield {
            "type": "action",
            "stage": "critic",
            "label": f"Scoring {len(candidates)} candidates with critic pass…",
        }
        ranked = await _critic_prune(candidates, model, max_suggestions)
        kept_strings = _candidates_to_strings(ranked)
        if kept_strings:
            suggestions = _specificify_suggestions(kept_strings, prompt, max_items=max_suggestions)
        else:
            suggestions = fallback
        autonomous_notes = [
            f"critic verdict: {len(ranked)} kept of {len(candidates)} generated"
        ] if candidates else []
    except Exception:
        suggestions = fallback
        autonomous_notes = []

    suggestion_rows = [
        {"id": f"suggestion-{idx + 1}", "text": str(t), "source": "autonomous"}
        for idx, t in enumerate(suggestions)
    ]
    yield {
        "type": "result",
        "prompt": prompt,
        "model": model,
        "focus": focus,
        "requires_confirmation": True,
        "autonomous_notes": autonomous_notes,
        "suggestions": suggestion_rows,
    }


async def _strengthen_self_improve_prompt(prompt: str) -> dict[str, Any]:
    """Rewrite a vague user request into a structured self-improve spec.

    Returns: strengthened_prompt (backward-compatible), objective,
    acceptance_criteria, scope_files, risks, model.
    """
    settings = settings_store.get()
    model = str(settings.get("model", "qwen2.5-coder:14b"))
    cleaned = str(prompt or "").strip()
    llm_user = f"User request to strengthen:\n{cleaned}"
    base_result = {
        "strengthened_prompt": cleaned,
        "objective": "",
        "acceptance_criteria": [],
        "scope_files": [],
        "risks": [],
        "model": model,
    }
    try:
        text = await ollama_client.chat_full(
            model=model,
            messages=[
                {"role": "system", "content": SELF_IMPROVE_STRENGTHEN},
                {"role": "user", "content": llm_user},
            ],
            temperature=0.2,
        )
        parsed = _safe_parse_json_object(text) or {}
        if not isinstance(parsed, dict):
            return base_result

        def _str_list(key: str) -> list[str]:
            v = parsed.get(key)
            if not isinstance(v, list):
                return []
            return [str(item).strip() for item in v if str(item or "").strip()]

        strengthened = str(parsed.get("strengthened_prompt") or "").strip() or cleaned
        return {
            "strengthened_prompt": strengthened,
            "objective": str(parsed.get("objective") or "").strip(),
            "acceptance_criteria": _str_list("acceptance_criteria"),
            "scope_files": _str_list("scope_files"),
            "risks": _str_list("risks"),
            "model": model,
        }
    except Exception:
        return base_result
