"""Validation script for the rebuilt research pipeline."""

from __future__ import annotations

import json
import time
from pathlib import Path
import sys
from typing import Any

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from main import app
from agent_space import web_research


def _run_query(client: TestClient, query: str, force_live: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    resp = client.get(
        "/api/agent-space/research/run",
        params={"q": query, "force_live": "true" if force_live else "false", "max_results": 10},
    )
    elapsed = time.perf_counter() - started
    payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    return {
        "status_code": resp.status_code,
        "elapsed_seconds": round(elapsed, 3),
        "ok": bool(payload.get("ok")),
        "from_memory": bool(payload.get("from_memory")),
        "source_count": len(list(payload.get("sources") or [])),
        "raw_mode": bool(payload.get("raw_mode")),
        "timings": dict(payload.get("timings") or {}),
        "answer_preview": str(payload.get("answer") or "")[:220],
        "provider_errors": dict(payload.get("provider_errors") or {}),
    }


def main() -> None:
    scenarios = [
        "latest advances in transformer architecture 2025",
        "what is SMOTE oversampling technique",
        "SpaceX launches 2025",
    ]
    results: dict[str, Any] = {"generated_at": time.time(), "scenarios": []}

    with TestClient(app) as client:
        status_resp = client.get("/api/agent-space/research/status")
        results["service_status"] = status_resp.json() if status_resp.status_code == 200 else {"status_code": status_resp.status_code}

        for query in scenarios:
            run = _run_query(client, query, force_live=False)
            run["query"] = query
            results["scenarios"].append(run)

        cache_query = "what is SMOTE oversampling technique"
        first = _run_query(client, cache_query, force_live=False)
        second = _run_query(client, cache_query, force_live=False)
        results["cache_repeat"] = {"query": cache_query, "first": first, "second": second}

        original_search_searxng = web_research.search_searxng

        async def _broken_searxng(query: str, limit: int = 8, *, intent: str = "general"):
            raise RuntimeError("forced_searxng_down")

        try:
            web_research.search_searxng = _broken_searxng  # type: ignore[assignment]
            fallback = _run_query(client, "SpaceX launches 2025", force_live=True)
            results["searxng_forced_down"] = fallback
        finally:
            web_research.search_searxng = original_search_searxng  # type: ignore[assignment]

    output_path = BACKEND_ROOT.parent / "SEARCH_TEST_RESULTS.md"
    lines = [
        "# SEARCH_TEST_RESULTS",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Service Status",
        "```json",
        json.dumps(results.get("service_status", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## Scenario Runs",
    ]
    for row in list(results.get("scenarios") or []):
        lines.extend(
            [
                f"### Query: {row.get('query')}",
                "```json",
                json.dumps(row, indent=2, ensure_ascii=False),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Cache Repeat",
            "```json",
            json.dumps(results.get("cache_repeat", {}), indent=2, ensure_ascii=False),
            "```",
            "",
            "## SearXNG Forced Down",
            "```json",
            json.dumps(results.get("searxng_forced_down", {}), indent=2, ensure_ascii=False),
            "```",
            "",
        ]
    )
    content = "\n".join(lines)
    try:
        output_path.write_text(content, encoding="utf-8")
    except PermissionError:
        output_path = BACKEND_ROOT / "SEARCH_TEST_RESULTS.md"
        output_path.write_text(content, encoding="utf-8")
    print(f"SEARCH TEST RESULTS WRITTEN: {output_path}")


if __name__ == "__main__":
    main()
