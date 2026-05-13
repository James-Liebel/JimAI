"""Purpose: Modular Agent Space browser route registration. Date: 2026-03-10."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
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


class BrowserUploadRequest(BaseModel):
    selector: str
    paths: list[str]


class BrowserFileChooserRequest(BaseModel):
    trigger_selector: str
    paths: list[str]
    timeout_ms: int = 15000


class BrowserDownloadRequest(BaseModel):
    selector: str
    save_as: str = ""
    timeout_ms: int = 60000


class BrowserReadDownloadRequest(BaseModel):
    filename: str
    max_bytes: int = 524288


class BrowserHoverActionRequest(BaseModel):
    selector: str = ""
    x: float | None = None
    y: float | None = None


class BrowserRightClickRequest(BaseModel):
    selector: str


class BrowserDoubleClickRequest(BaseModel):
    selector: str


class BrowserDragRequest(BaseModel):
    source: str
    target: str


class BrowserKeyChordRequest(BaseModel):
    keys: list[str]
    selector: str = ""


class BrowserSelectTextRequest(BaseModel):
    selector: str
    start: int = 0
    end: int = -1


class BrowserClipboardCopyRequest(BaseModel):
    selector: str = ""


class BrowserClipboardPasteRequest(BaseModel):
    selector: str = ""
    text: str = ""


class BrowserNewTabRequest(BaseModel):
    url: str = ""


class BrowserSwitchIframeRequest(BaseModel):
    selector: str


class BrowserDialogRequest(BaseModel):
    action: str = "accept"
    prompt_text: str = ""


class BrowserFindInPageRequest(BaseModel):
    query: str
    case_sensitive: bool = False


class BrowserSavePdfRequest(BaseModel):
    filename: str = "page.pdf"


class BrowserZoomRequest(BaseModel):
    factor: float = 1.0


class BrowserCookiesQueryRequest(BaseModel):
    urls: list[str] | None = None


class BrowserSetCookieRequest(BaseModel):
    name: str
    value: str
    url: str = ""
    domain: str = ""
    path: str = "/"


class BrowserGeolocationRequest(BaseModel):
    latitude: float
    longitude: float
    accuracy: float = 50.0


class BrowserWheelRequest(BaseModel):
    dx: float = 0.0
    dy: float = 400.0
    x: float | None = None
    y: float | None = None


class BrowserTouchTapRequest(BaseModel):
    x: float
    y: float


class BrowserWaitForUrlRequest(BaseModel):
    pattern: str
    timeout_ms: int = 30000


class AtlasChatRequest(BaseModel):
    message: str
    url: str = ""
    title: str = ""
    page_text: str = ""
    history: list[dict] = []
    screenshot: str = ""
    action_feedback: str = ""
    # URL the page had BEFORE the most recent agent action ran. The backend's
    # dedup gate compares this against the current ``url`` to detect no-op
    # repeats. Defaults to "" so existing callers keep working.
    last_url: str = ""


class BenchmarkResultRequest(BaseModel):
    taskId: str
    status: str
    stepsUsed: int = 0
    finalUrl: str = ""
    finalPageText: str = ""
    agentFinalResponse: str = ""
    agentSaidDone: bool = False
    gradeReason: str = ""
    timestamp: float = 0.0


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

    @router.post("/browser/sessions/{session_id}/upload")
    async def browser_upload(session_id: str, req: BrowserUploadRequest) -> dict[str, Any]:
        return await browser_manager.upload_file(
            session_id,
            selector=req.selector,
            paths=req.paths,
        )

    @router.post("/browser/sessions/{session_id}/file-chooser")
    async def browser_file_chooser(session_id: str, req: BrowserFileChooserRequest) -> dict[str, Any]:
        return await browser_manager.accept_next_file_chooser(
            session_id,
            trigger_selector=req.trigger_selector,
            paths=req.paths,
            timeout_ms=req.timeout_ms,
        )

    @router.post("/browser/sessions/{session_id}/download")
    async def browser_download(session_id: str, req: BrowserDownloadRequest) -> dict[str, Any]:
        return await browser_manager.download_via_click(
            session_id,
            selector=req.selector,
            save_as=req.save_as,
            timeout_ms=req.timeout_ms,
        )

    @router.get("/browser/sessions/{session_id}/downloads")
    async def browser_list_downloads(session_id: str) -> dict[str, Any]:
        return await browser_manager.list_downloads(session_id)

    @router.post("/browser/sessions/{session_id}/downloads/read")
    async def browser_read_download(session_id: str, req: BrowserReadDownloadRequest) -> dict[str, Any]:
        return await browser_manager.read_download(
            session_id,
            filename=req.filename,
            max_bytes=req.max_bytes,
        )

    @router.post("/browser/sessions/{session_id}/hover-action")
    async def browser_hover_action(session_id: str, req: BrowserHoverActionRequest) -> dict[str, Any]:
        return await browser_manager.hover(session_id, selector=req.selector, x=req.x, y=req.y)

    @router.post("/browser/sessions/{session_id}/right-click")
    async def browser_right_click(session_id: str, req: BrowserRightClickRequest) -> dict[str, Any]:
        return await browser_manager.right_click(session_id, selector=req.selector)

    @router.post("/browser/sessions/{session_id}/double-click")
    async def browser_double_click(session_id: str, req: BrowserDoubleClickRequest) -> dict[str, Any]:
        return await browser_manager.double_click(session_id, selector=req.selector)

    @router.post("/browser/sessions/{session_id}/drag")
    async def browser_drag(session_id: str, req: BrowserDragRequest) -> dict[str, Any]:
        return await browser_manager.drag_and_drop(session_id, source=req.source, target=req.target)

    @router.post("/browser/sessions/{session_id}/key-chord")
    async def browser_key_chord(session_id: str, req: BrowserKeyChordRequest) -> dict[str, Any]:
        return await browser_manager.key_chord(session_id, keys=req.keys, selector=req.selector)

    @router.post("/browser/sessions/{session_id}/select-text")
    async def browser_select_text(session_id: str, req: BrowserSelectTextRequest) -> dict[str, Any]:
        return await browser_manager.select_text(session_id, selector=req.selector, start=req.start, end=req.end)

    @router.post("/browser/sessions/{session_id}/clipboard/copy")
    async def browser_clipboard_copy(session_id: str, req: BrowserClipboardCopyRequest) -> dict[str, Any]:
        return await browser_manager.clipboard_copy(session_id, selector=req.selector)

    @router.post("/browser/sessions/{session_id}/clipboard/paste")
    async def browser_clipboard_paste(session_id: str, req: BrowserClipboardPasteRequest) -> dict[str, Any]:
        return await browser_manager.clipboard_paste(session_id, selector=req.selector, text=req.text)

    @router.post("/browser/sessions/{session_id}/history/back")
    async def browser_go_back(session_id: str) -> dict[str, Any]:
        return await browser_manager.go_back(session_id)

    @router.post("/browser/sessions/{session_id}/history/forward")
    async def browser_go_forward(session_id: str) -> dict[str, Any]:
        return await browser_manager.go_forward(session_id)

    @router.post("/browser/sessions/{session_id}/reload")
    async def browser_reload(session_id: str) -> dict[str, Any]:
        return await browser_manager.reload(session_id)

    @router.post("/browser/sessions/{session_id}/new-tab")
    async def browser_new_tab(session_id: str, req: BrowserNewTabRequest) -> dict[str, Any]:
        return await browser_manager.new_tab(session_id, url=req.url)

    @router.post("/browser/sessions/{session_id}/iframe/enter")
    async def browser_iframe_enter(session_id: str, req: BrowserSwitchIframeRequest) -> dict[str, Any]:
        return await browser_manager.switch_to_iframe(session_id, selector=req.selector)

    @router.post("/browser/sessions/{session_id}/iframe/leave")
    async def browser_iframe_leave(session_id: str) -> dict[str, Any]:
        return await browser_manager.switch_to_top(session_id)

    @router.post("/browser/sessions/{session_id}/dialog")
    async def browser_handle_dialog(session_id: str, req: BrowserDialogRequest) -> dict[str, Any]:
        return await browser_manager.handle_next_dialog(session_id, action=req.action, prompt_text=req.prompt_text)

    @router.post("/browser/sessions/{session_id}/find")
    async def browser_find_in_page(session_id: str, req: BrowserFindInPageRequest) -> dict[str, Any]:
        return await browser_manager.find_in_page(session_id, query=req.query, case_sensitive=req.case_sensitive)

    @router.post("/browser/sessions/{session_id}/save-pdf")
    async def browser_save_pdf(session_id: str, req: BrowserSavePdfRequest) -> dict[str, Any]:
        return await browser_manager.save_as_pdf(session_id, filename=req.filename)

    @router.post("/browser/sessions/{session_id}/zoom")
    async def browser_set_zoom(session_id: str, req: BrowserZoomRequest) -> dict[str, Any]:
        return await browser_manager.set_zoom(session_id, factor=req.factor)

    @router.post("/browser/sessions/{session_id}/cookies/query")
    async def browser_cookies_query(session_id: str, req: BrowserCookiesQueryRequest) -> dict[str, Any]:
        return await browser_manager.get_cookies(session_id, urls=req.urls)

    @router.post("/browser/sessions/{session_id}/cookies/set")
    async def browser_cookies_set(session_id: str, req: BrowserSetCookieRequest) -> dict[str, Any]:
        return await browser_manager.set_cookie(
            session_id, name=req.name, value=req.value, url=req.url, domain=req.domain, path=req.path,
        )

    @router.post("/browser/sessions/{session_id}/cookies/clear")
    async def browser_cookies_clear(session_id: str) -> dict[str, Any]:
        return await browser_manager.clear_cookies(session_id)

    @router.post("/browser/sessions/{session_id}/geolocation")
    async def browser_set_geolocation(session_id: str, req: BrowserGeolocationRequest) -> dict[str, Any]:
        return await browser_manager.set_geolocation(
            session_id, latitude=req.latitude, longitude=req.longitude, accuracy=req.accuracy,
        )

    @router.get("/browser/sessions/{session_id}/source")
    async def browser_view_source(session_id: str) -> dict[str, Any]:
        return await browser_manager.view_source(session_id)

    @router.post("/browser/sessions/{session_id}/wheel")
    async def browser_wheel(session_id: str, req: BrowserWheelRequest) -> dict[str, Any]:
        return await browser_manager.mouse_wheel(session_id, dx=req.dx, dy=req.dy, x=req.x, y=req.y)

    @router.post("/browser/sessions/{session_id}/touch-tap")
    async def browser_touch_tap(session_id: str, req: BrowserTouchTapRequest) -> dict[str, Any]:
        return await browser_manager.touch_tap(session_id, x=req.x, y=req.y)

    @router.post("/browser/sessions/{session_id}/wait-for-url")
    async def browser_wait_for_url(session_id: str, req: BrowserWaitForUrlRequest) -> dict[str, Any]:
        return await browser_manager.wait_for_url(session_id, pattern=req.pattern, timeout_ms=req.timeout_ms)

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

    @router.post("/browser/atlas/chat")
    async def browser_atlas_chat(req: AtlasChatRequest) -> dict[str, Any]:
        from agent_space.browser_agent_runner import chat_browser_step
        return await chat_browser_step(
            message=req.message,
            url=req.url,
            title=req.title,
            page_text=req.page_text,
            history=req.history,
            screenshot=req.screenshot,
            action_feedback=req.action_feedback,
            last_url=req.last_url,
        )

    @router.post("/benchmark/results")
    async def benchmark_save_result(req: BenchmarkResultRequest) -> dict[str, Any]:
        from .paths import SELF_IMPROVEMENT_DIR
        results_file = SELF_IMPROVEMENT_DIR / "benchmark_results.jsonl"
        entry = req.model_dump()
        entry["saved_at"] = datetime.now(timezone.utc).isoformat()
        with results_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return {"ok": True}

    @router.get("/benchmark/results")
    async def benchmark_get_results() -> list[dict[str, Any]]:
        from .paths import SELF_IMPROVEMENT_DIR
        results_file = SELF_IMPROVEMENT_DIR / "benchmark_results.jsonl"
        if not results_file.exists():
            return []
        results = []
        for line in results_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except Exception:
                    pass
        return results

    @router.delete("/benchmark/results")
    async def benchmark_clear_results() -> dict[str, Any]:
        from .paths import SELF_IMPROVEMENT_DIR
        results_file = SELF_IMPROVEMENT_DIR / "benchmark_results.jsonl"
        if results_file.exists():
            results_file.unlink()
        return {"ok": True}

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
