"""Purpose: Modular Agent Space browser route registration. Date: 2026-03-10."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel


class BrowserOpenRequest(BaseModel):
    url: str = ""
    headless: bool = True


class BrowserNavigateRequest(BaseModel):
    url: str


class BrowserClickRequest(BaseModel):
    selector: str


class BrowserTypeRequest(BaseModel):
    selector: str
    text: str
    press_enter: bool = False


class BrowserExtractRequest(BaseModel):
    selector: str = "body"
    max_chars: int = 12000


class BrowserScreenshotRequest(BaseModel):
    full_page: bool = True


class BrowserCursorMoveRequest(BaseModel):
    x: float
    y: float
    steps: int = 1


class BrowserCursorClickRequest(BaseModel):
    x: float | None = None
    y: float | None = None
    button: str = "left"
    click_count: int = 1
    delay_ms: int = 0


class BrowserCursorScrollRequest(BaseModel):
    dx: float = 0.0
    dy: float = 600.0
    x: float | None = None
    y: float | None = None


class BrowserHoverRequest(BaseModel):
    selector: str = ""
    x: float | None = None
    y: float | None = None


def register_browser_routes(
    router: APIRouter,
    *,
    browser_manager: Any,
) -> None:
    @router.get("/browser/sessions")
    async def browser_sessions() -> list[dict[str, Any]]:
        return await browser_manager.list_sessions()

    @router.post("/browser/sessions")
    async def browser_open(req: BrowserOpenRequest) -> dict[str, Any]:
        return await browser_manager.open_session(url=req.url, headless=req.headless)

    @router.post("/browser/sessions/{session_id}/navigate")
    async def browser_navigate(session_id: str, req: BrowserNavigateRequest) -> dict[str, Any]:
        return await browser_manager.navigate(session_id, req.url)

    @router.post("/browser/sessions/{session_id}/click")
    async def browser_click(session_id: str, req: BrowserClickRequest) -> dict[str, Any]:
        return await browser_manager.click(session_id, req.selector)

    @router.post("/browser/sessions/{session_id}/type")
    async def browser_type(session_id: str, req: BrowserTypeRequest) -> dict[str, Any]:
        return await browser_manager.type_text(
            session_id,
            selector=req.selector,
            text=req.text,
            press_enter=req.press_enter,
        )

    @router.post("/browser/sessions/{session_id}/extract")
    async def browser_extract(session_id: str, req: BrowserExtractRequest) -> dict[str, Any]:
        return await browser_manager.extract_text(
            session_id,
            selector=req.selector,
            max_chars=req.max_chars,
        )

    @router.post("/browser/sessions/{session_id}/screenshot")
    async def browser_screenshot(session_id: str, req: BrowserScreenshotRequest) -> dict[str, Any]:
        return await browser_manager.screenshot(session_id, full_page=req.full_page)

    @router.get("/browser/sessions/{session_id}/state")
    async def browser_state(
        session_id: str,
        include_links: bool = Query(default=False),
        link_limit: int = Query(default=40, ge=1, le=300),
    ) -> dict[str, Any]:
        return await browser_manager.get_state(session_id, include_links=include_links, link_limit=link_limit)

    @router.get("/browser/sessions/{session_id}/links")
    async def browser_links(session_id: str, limit: int = Query(default=40, ge=1, le=300)) -> dict[str, Any]:
        return await browser_manager.list_links(session_id, limit=limit)

    @router.post("/browser/sessions/{session_id}/cursor/move")
    async def browser_cursor_move(session_id: str, req: BrowserCursorMoveRequest) -> dict[str, Any]:
        return await browser_manager.cursor_move(
            session_id,
            x=req.x,
            y=req.y,
            steps=req.steps,
        )

    @router.post("/browser/sessions/{session_id}/cursor/click")
    async def browser_cursor_click(session_id: str, req: BrowserCursorClickRequest) -> dict[str, Any]:
        return await browser_manager.cursor_click(
            session_id,
            x=req.x,
            y=req.y,
            button=req.button,
            click_count=req.click_count,
            delay_ms=req.delay_ms,
        )

    @router.post("/browser/sessions/{session_id}/cursor/scroll")
    async def browser_cursor_scroll(session_id: str, req: BrowserCursorScrollRequest) -> dict[str, Any]:
        return await browser_manager.cursor_scroll(
            session_id,
            dx=req.dx,
            dy=req.dy,
            x=req.x,
            y=req.y,
        )

    @router.post("/browser/sessions/{session_id}/cursor/hover")
    async def browser_cursor_hover(session_id: str, req: BrowserHoverRequest) -> dict[str, Any]:
        return await browser_manager.cursor_hover(
            session_id,
            selector=req.selector,
            x=req.x,
            y=req.y,
        )

    @router.post("/browser/sessions/{session_id}/close")
    async def browser_close(session_id: str) -> dict[str, Any]:
        return await browser_manager.close_session(session_id)

    @router.post("/browser/close-all")
    async def browser_close_all() -> dict[str, Any]:
        return await browser_manager.close_all()
