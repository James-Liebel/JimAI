"""Purpose: Modular Agent Space browser route registration. Date: 2026-03-10."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel


class BrowserOpenRequest(BaseModel):
    url: str = ""
    headless: bool = True
    viewport_width: int | None = None
    viewport_height: int | None = None
    user_agent: str = ""
    locale: str = ""
    timezone_id: str = ""
    ignore_https_errors: bool = False
    slow_mo_ms: int = 0


class BrowserNavigateRequest(BaseModel):
    url: str


class BrowserClickRequest(BaseModel):
    selector: str


class BrowserTypeRequest(BaseModel):
    selector: str
    text: str
    press_enter: bool = False
    clear_first: bool = True


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


class BrowserScrollPageRequest(BaseModel):
    delta_x: float = 0.0
    delta_y: float = 0.0
    position: str = ""


class BrowserSelectRequest(BaseModel):
    selector: str
    value: str = ""
    label: str = ""


class BrowserCheckRequest(BaseModel):
    selector: str
    checked: bool = True


class BrowserPressKeyRequest(BaseModel):
    key: str
    selector: str = ""


class BrowserWaitForRequest(BaseModel):
    selector: str
    state: str = "visible"
    timeout_ms: int = 30000


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
        return await browser_manager.open_session(
            url=req.url,
            headless=req.headless,
            viewport_width=req.viewport_width,
            viewport_height=req.viewport_height,
            user_agent=req.user_agent,
            locale=req.locale,
            timezone_id=req.timezone_id,
            ignore_https_errors=req.ignore_https_errors,
            slow_mo_ms=req.slow_mo_ms,
        )

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
            clear_first=req.clear_first,
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

    @router.post("/browser/sessions/{session_id}/scroll-page")
    async def browser_scroll_page(session_id: str, req: BrowserScrollPageRequest) -> dict[str, Any]:
        return await browser_manager.scroll_page(
            session_id,
            delta_x=req.delta_x,
            delta_y=req.delta_y,
            position=req.position,
        )

    @router.post("/browser/sessions/{session_id}/scroll-into-view")
    async def browser_scroll_into_view(session_id: str, req: BrowserClickRequest) -> dict[str, Any]:
        return await browser_manager.scroll_into_view(session_id, selector=req.selector)

    @router.post("/browser/sessions/{session_id}/select")
    async def browser_select(session_id: str, req: BrowserSelectRequest) -> dict[str, Any]:
        return await browser_manager.select_option(
            session_id,
            selector=req.selector,
            value=req.value,
            label=req.label,
        )

    @router.post("/browser/sessions/{session_id}/check")
    async def browser_check(session_id: str, req: BrowserCheckRequest) -> dict[str, Any]:
        return await browser_manager.set_checked(session_id, selector=req.selector, checked=req.checked)

    @router.post("/browser/sessions/{session_id}/press-key")
    async def browser_press_key(session_id: str, req: BrowserPressKeyRequest) -> dict[str, Any]:
        return await browser_manager.press_key(session_id, key=req.key, selector=req.selector)

    @router.post("/browser/sessions/{session_id}/wait-for")
    async def browser_wait_for(session_id: str, req: BrowserWaitForRequest) -> dict[str, Any]:
        return await browser_manager.wait_for(
            session_id,
            selector=req.selector,
            state=req.state,
            timeout_ms=req.timeout_ms,
        )

    @router.get("/browser/sessions/{session_id}/interactive")
    async def browser_interactive(session_id: str, limit: int = Query(default=80, ge=1, le=200)) -> dict[str, Any]:
        return await browser_manager.list_interactive(session_id, limit=limit)

    @router.post("/browser/sessions/{session_id}/close")
    async def browser_close(session_id: str) -> dict[str, Any]:
        return await browser_manager.close_session(session_id)

    @router.post("/browser/close-all")
    async def browser_close_all() -> dict[str, Any]:
        return await browser_manager.close_all()

    @router.post("/browser/atlas/open")
    async def browser_atlas_open(
        url: str = Query(default="https://www.google.com"),
        profile_dir: str = Query(default=""),
    ) -> dict[str, Any]:
        return await browser_manager.open_atlas_session(url=url, profile_dir=profile_dir)

    @router.get("/browser/agent/run")
    async def browser_agent_run(
        goal: str = Query(..., min_length=1),
        url: str = Query(default="about:blank"),
        max_steps: int = Query(default=20, ge=1, le=40),
        headless: bool = Query(default=False),
    ) -> StreamingResponse:
        from .browser_agent_runner import run_browser_agent

        async def _sse():
            async for event in run_browser_agent(
                goal,
                url,
                browser_manager=browser_manager,
                max_steps=max_steps,
                headless=headless,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield 'data: {"type":"keepalive"}\n\n'

        return StreamingResponse(
            _sse(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
