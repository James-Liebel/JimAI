"""Purpose: Modular Agent Space chat/research route registration. Date: 2026-03-10."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .web_research import (
    fetch_web,
    get_research_service_status,
    research_once,
    research_stream,
    search_web,
)


class ChatMessageRequest(BaseModel):
    role: str
    content: str


def register_chat_research_routes(
    router: APIRouter,
    *,
    chat_store: Any,
) -> None:
    def _research_sse_stream(
        query: str,
        *,
        force_live: bool,
        model: str | None,
        max_results: int,
    ) -> StreamingResponse:
        async def _generator():
            async for event in research_stream(
                query,
                force_live=force_live,
                model=model,
                max_results=max_results,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            # Keep transport compatible with existing SSE consumers.
            yield 'data: {"type":"keepalive"}\n\n'

        return StreamingResponse(
            _generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/research/search")
    async def research_search(
        q: str = Query(..., min_length=1),
        limit: int = Query(default=8, ge=1, le=20),
    ) -> dict[str, Any]:
        return await search_web(q, limit=limit)

    @router.get("/research/fetch")
    async def research_fetch(url: str = Query(..., min_length=5)) -> dict[str, Any]:
        return await fetch_web(url)

    @router.get("/research/status")
    async def research_status() -> dict[str, Any]:
        return await get_research_service_status()

    @router.get("/research/run")
    async def research_run(
        q: str = Query(..., min_length=1),
        force_live: bool = Query(default=False),
        max_results: int = Query(default=10, ge=1, le=20),
        model: str | None = Query(default=None),
    ) -> dict[str, Any]:
        return await research_once(
            q,
            force_live=force_live,
            model=model,
            max_results=max_results,
        )

    @router.get("/research/stream")
    async def research_stream_route(
        q: str = Query(..., min_length=1),
        force_live: bool = Query(default=False),
        max_results: int = Query(default=10, ge=1, le=20),
        model: str | None = Query(default=None),
    ) -> StreamingResponse:
        return _research_sse_stream(
            q,
            force_live=force_live,
            model=model,
            max_results=max_results,
        )

    @router.get("/chat/threads")
    async def chat_threads(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
        return chat_store.list_threads(limit=limit)

    @router.get("/chat/threads/{thread_id}")
    async def chat_thread(thread_id: str) -> dict[str, Any]:
        return chat_store.get_thread(thread_id)

    @router.post("/chat/threads/{thread_id}/message")
    async def chat_add_message(thread_id: str, req: ChatMessageRequest) -> dict[str, Any]:
        return chat_store.append_message(thread_id, role=req.role, content=req.content)
