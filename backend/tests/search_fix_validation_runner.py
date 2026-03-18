"""Run targeted validation for critical search pipeline bug fixes."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agent_space import web_research


def _is_bing_redirect(url: str) -> bool:
    raw = str(url or "").strip().lower()
    if not raw:
        return False
    try:
        parsed = urlparse(raw)
    except Exception:
        return False
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    if "bing.com" not in host:
        return False
    if path.startswith("/ck/") or path.startswith("/aclick") or path.startswith("/fd/ls"):
        return True
    params = parse_qs(parsed.query or "")
    return "u" in params


def _answer_quality(answer: str, sources: list[dict]) -> str:
    low = str(answer or "").lower()
    if "could not retrieve live web results" in low:
        return "honest_failure"
    if "search returned irrelevant results" in low:
        return "honest_failure"
    if not sources:
        return "honest_failure"
    if "[" in answer and "]" in answer:
        return "correct_or_grounded"
    return "uncertain"


async def _run_one(query: str) -> dict:
    started = time.perf_counter()
    intent = web_research.detect_query_intent(query)
    rewritten, used_rewrite = await web_research.rewrite_query_variants(
        query,
        timeout_seconds=web_research.QUERY_REWRITE_TIMEOUT_S,
    )
    search_data = await web_research._parallel_search(rewritten[:3], limit=8, intent=intent)
    rows = list(search_data.get("rows") or [])[:10]
    scored = web_research.score_relevance(query, rows)
    scored.sort(key=lambda item: item[0], reverse=True)
    before_scores = [round(float(score), 4) for score, _ in scored]
    filtered_scores = [round(float(score), 4) for score, _ in scored if float(score) >= 0.15]
    engines = sorted({str(row.get("engine") or "").strip() for row in rows if str(row.get("engine") or "").strip()})
    bing_redirects = sum(1 for row in rows if _is_bing_redirect(str(row.get("url") or "")))

    result = await web_research.research_once(query, force_live=True, max_results=10)
    timings = dict(result.get("timings") or {})
    answer = str(result.get("answer") or "")
    sources = list(result.get("sources") or [])

    return {
        "query": query,
        "intent": intent,
        "used_rewrite": bool(used_rewrite),
        "rewritten_queries": list(rewritten),
        "engines_returned": engines,
        "rows_returned": len(rows),
        "bing_redirect_urls": bing_redirects,
        "relevance_before_filter": before_scores,
        "relevance_after_filter": filtered_scores,
        "time_to_first_ollama_token_seconds": timings.get("ollama_first_token"),
        "timings": timings,
        "provider_errors": dict(result.get("provider_errors") or {}),
        "answer_quality": _answer_quality(answer, sources),
        "answer_preview": answer[:280],
        "source_count": len(sources),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


async def _main() -> None:
    queries = [
        "what is the cost of franklin batting gloves",
        "latest transformer architecture research 2025",
        "best mlops tools 2025",
    ]
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": [],
    }
    sample_bing = "https://www.bing.com/ck/a?u=aHR0cHM6Ly9leGFtcGxlLmNvbS9wYWdlP3g9MQ=="
    resolved = web_research.resolve_bing_url(sample_bing)
    payload["bing_decode_check"] = {
        "sample": sample_bing,
        "resolved": resolved,
        "ok": resolved.startswith("https://example.com/"),
    }
    for query in queries:
        payload["results"].append(await _run_one(query))
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(_main())
