"""Validation script for chat auto web lookup and stale-answer correction."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from main import app
from api import chat as chat_api


def _parse_sse(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if not payload:
            continue
        try:
            events.append(json.loads(payload))
        except Exception:
            continue
    return events


def main() -> None:
    original_search_web = chat_api.search_web
    original_fetch_web = chat_api.fetch_web
    original_chat_stream = chat_api.ollama_client.chat_stream
    original_vectordb_retrieve = chat_api.vectordb.retrieve
    original_compare_enabled = chat_api.COMPARE_MODELS_ENABLED
    original_layered_review = chat_api.LAYERED_REVIEW_ENABLED
    original_should_judge = chat_api.should_judge

    search_queries: list[str] = []

    async def fake_search_web(query: str, limit: int = 8) -> dict[str, Any]:
        search_queries.append(query)
        return {
            "ok": True,
            "offline": False,
            "query": query,
            "results": [
                {
                    "title": "Men's Batting Gloves - Dick's Sporting Goods",
                    "url": "https://www.dickssportinggoods.com/search/SearchDisplay?searchTerm=mens+batting+gloves",
                    "snippet": "Shop men's batting gloves at Dick's Sporting Goods. Current listings and promotions available.",
                },
                {
                    "title": "Baseball Batting Gloves Sale",
                    "url": "https://www.dickssportinggoods.com/f/baseball-batting-gloves",
                    "snippet": "Find baseball batting gloves from top brands with multiple price points.",
                },
            ][: max(1, limit)],
        }

    async def fake_fetch_web(url: str, max_chars: int = 12000) -> dict[str, Any]:
        text = (
            "Men's batting gloves collection with listed prices including examples around $24.99, $29.99, and $39.99. "
            "Inventory and promotions vary by size and location."
        )
        return {
            "ok": True,
            "offline": False,
            "url": url,
            "title": "Dick's Sporting Goods Batting Gloves",
            "text": text[:max_chars],
            "cached": False,
            "stale": False,
        }

    async def fake_chat_stream(*args: Any, **kwargs: Any):
        # Intentionally stale-style response to trigger correction path.
        yield "As of my knowledge cutoff, I cannot provide current pricing."

    async def fake_vectordb_retrieve(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    try:
        chat_api.search_web = fake_search_web  # type: ignore[assignment]
        chat_api.fetch_web = fake_fetch_web  # type: ignore[assignment]
        chat_api.ollama_client.chat_stream = fake_chat_stream  # type: ignore[assignment]
        chat_api.vectordb.retrieve = fake_vectordb_retrieve  # type: ignore[assignment]
        chat_api.COMPARE_MODELS_ENABLED = False
        chat_api.LAYERED_REVIEW_ENABLED = False
        chat_api.should_judge = lambda *_args, **_kwargs: False  # type: ignore[assignment]

        with TestClient(app) as client:
            resp = client.post(
                "/api/chat",
                json={
                    "message": "I need current batting glove prices from dicks sporting goods for mens baseball",
                    "mode": "chat",
                    "session_id": "chat-live-validation",
                    "history": [],
                },
            )
            resp.raise_for_status()
            events = _parse_sse(resp.text)
            assert events, "Expected SSE events from chat endpoint."

            text_output = "".join(str(evt.get("text", "")) for evt in events if not bool(evt.get("done")))
            done = next((evt for evt in reversed(events) if bool(evt.get("done"))), None)
            assert isinstance(done, dict), "Missing final done event."
            routing = dict(done.get("routing") or {})

            print(
                "CHAT LIVE LOOKUP ROUTING:",
                {
                    "auto_web_research_attempted": routing.get("auto_web_research_attempted"),
                    "auto_web_research_results": routing.get("auto_web_research_results"),
                    "auto_web_research_domain_count": routing.get("auto_web_research_domain_count"),
                    "auto_web_research_query_count": routing.get("auto_web_research_query_count"),
                    "auto_web_research_fetched_pages": routing.get("auto_web_research_fetched_pages"),
                    "stale_response_corrected": routing.get("stale_response_corrected"),
                },
            )
            print("CHAT OUTPUT PREVIEW:", text_output[:220])
            print("CHAT QUERIES EXECUTED:", len(search_queries), search_queries[:6])

            assert routing.get("auto_web_research_attempted") is True
            assert int(routing.get("auto_web_research_results") or 0) >= 1
            assert int(routing.get("auto_web_research_query_count") or 0) >= 2
            assert int(routing.get("auto_web_research_fetched_pages") or 0) >= 1
            assert len(search_queries) >= 2
            assert routing.get("stale_response_corrected") is True
            assert "I performed live web lookup" in text_output
            print("CHAT LIVE LOOKUP VALIDATION RESULT: PASS")
    finally:
        chat_api.search_web = original_search_web  # type: ignore[assignment]
        chat_api.fetch_web = original_fetch_web  # type: ignore[assignment]
        chat_api.ollama_client.chat_stream = original_chat_stream  # type: ignore[assignment]
        chat_api.vectordb.retrieve = original_vectordb_retrieve  # type: ignore[assignment]
        chat_api.COMPARE_MODELS_ENABLED = original_compare_enabled
        chat_api.LAYERED_REVIEW_ENABLED = original_layered_review
        chat_api.should_judge = original_should_judge  # type: ignore[assignment]


if __name__ == "__main__":
    main()
