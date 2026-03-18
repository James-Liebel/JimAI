"""Headless browser manager for agent browsing workflows."""

from __future__ import annotations

import asyncio
import base64
import logging
import sys
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class BrowserAgentManager:
    """Maintains Playwright browser sessions for agents."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    async def _can_spawn_subprocess(self) -> tuple[bool, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                "print('ok')",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def _require_session(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Unknown session_id '{session_id}'.")
        return session

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        if value < lower:
            return lower
        if value > upper:
            return upper
        return value

    async def _collect_links(self, page: Any, limit: int = 40) -> list[dict[str, Any]]:
        try:
            rows = await page.evaluate(
                """(limit) => {
                    const out = [];
                    const anchors = Array.from(document.querySelectorAll('a[href]'));
                    for (let i = 0; i < anchors.length && out.length < limit; i += 1) {
                        const a = anchors[i];
                        const rect = a.getBoundingClientRect();
                        const text = (a.innerText || a.textContent || '').trim().replace(/\\s+/g, ' ');
                        if (!a.href) continue;
                        out.push({
                            href: a.href,
                            text: text.slice(0, 200),
                            x: rect.left,
                            y: rect.top,
                            width: rect.width,
                            height: rect.height,
                            visible: rect.width > 0 && rect.height > 0,
                        });
                    }
                    return out;
                }""",
                max(1, int(limit)),
            )
            if isinstance(rows, list):
                return rows
        except Exception:
            logger.exception("Failed to collect links from page")
        return []

    async def _capture_state(self, session_id: str, session: dict[str, Any]) -> dict[str, Any]:
        page = session.get("page")
        url = ""
        title = ""
        try:
            url = page.url if page else ""
        except Exception:
            url = ""
        try:
            title = await page.title() if page else ""
        except Exception:
            title = ""

        js_state = {
            "scroll_x": 0.0,
            "scroll_y": 0.0,
            "viewport_width": 0.0,
            "viewport_height": 0.0,
            "document_width": 0.0,
            "document_height": 0.0,
        }
        try:
            page_state = await page.evaluate(
                """() => ({
                    scroll_x: Number(window.scrollX || 0),
                    scroll_y: Number(window.scrollY || 0),
                    viewport_width: Number(window.innerWidth || 0),
                    viewport_height: Number(window.innerHeight || 0),
                    document_width: Number(document.documentElement?.scrollWidth || 0),
                    document_height: Number(document.documentElement?.scrollHeight || 0)
                })"""
            )
            if isinstance(page_state, dict):
                js_state.update(page_state)
        except Exception:
            logger.exception("Failed to evaluate page scroll/viewport state")

        viewport = page.viewport_size or {
            "width": int(js_state.get("viewport_width", 0) or 0),
            "height": int(js_state.get("viewport_height", 0) or 0),
        }
        cursor = dict(session.get("cursor") or {"x": 0.0, "y": 0.0})

        return {
            "session_id": session_id,
            "url": url,
            "title": title,
            "cursor": cursor,
            "viewport": viewport,
            "scroll": {
                "x": float(js_state.get("scroll_x", 0.0) or 0.0),
                "y": float(js_state.get("scroll_y", 0.0) or 0.0),
            },
            "document": {
                "width": float(js_state.get("document_width", 0.0) or 0.0),
                "height": float(js_state.get("document_height", 0.0) or 0.0),
            },
        }

    async def list_sessions(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for session_id, data in self._sessions.items():
            state = await self._capture_state(session_id, data)
            rows.append(
                {
                    "session_id": session_id,
                    "created_at": data.get("created_at"),
                    "headless": data.get("headless", True),
                    "url": state.get("url", ""),
                    "title": state.get("title", ""),
                    "cursor": state.get("cursor", {"x": 0.0, "y": 0.0}),
                    "scroll": state.get("scroll", {"x": 0.0, "y": 0.0}),
                }
            )
        rows.sort(key=lambda row: row.get("created_at", 0), reverse=True)
        return rows

    async def open_session(self, *, url: str = "", headless: bool = True) -> dict[str, Any]:
        can_spawn, spawn_error = await self._can_spawn_subprocess()
        if not can_spawn:
            return {"success": False, "error": f"Browser launch unavailable: {spawn_error}"}
        try:
            from playwright.async_api import async_playwright
        except Exception:
            return {
                "success": False,
                "error": "playwright is not installed. Install and run browser binaries.",
            }

        playwright = None
        browser = None
        context = None
        page = None
        try:
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(headless=headless)
            context = await browser.new_context()
            page = await context.new_page()
            if url:
                await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            viewport = page.viewport_size or {"width": 1280, "height": 720}
            session_id = str(uuid.uuid4())
            self._sessions[session_id] = {
                "playwright": playwright,
                "browser": browser,
                "context": context,
                "page": page,
                "created_at": time.time(),
                "headless": headless,
                "cursor": {
                    "x": float((viewport.get("width", 1280) or 1280) / 2.0),
                    "y": float((viewport.get("height", 720) or 720) / 2.0),
                },
            }
            state = await self._capture_state(session_id, self._sessions[session_id])
            return {
                "success": True,
                "session_id": session_id,
                "url": state["url"],
                "title": state["title"],
                "cursor": state["cursor"],
                "viewport": state["viewport"],
                "headless": headless,
            }
        except Exception as exc:
            try:
                if context:
                    await context.close()
            except Exception:
                logger.exception("Failed to close browser context during open_session cleanup")
            try:
                if browser:
                    await browser.close()
            except Exception:
                logger.exception("Failed to close browser during open_session cleanup")
            try:
                if playwright:
                    await playwright.stop()
            except Exception:
                logger.exception("Failed to stop playwright during open_session cleanup")
            return {"success": False, "error": str(exc)}

    async def navigate(self, session_id: str, url: str) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        if not url:
            return {"success": False, "error": "url is required."}
        try:
            page = session["page"]
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            state = await self._capture_state(session_id, session)
            return {"success": True, **state}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def click(self, session_id: str, selector: str) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        if not selector:
            return {"success": False, "error": "selector is required."}
        try:
            page = session["page"]
            await page.click(selector, timeout=10000)
            try:
                box = await page.locator(selector).first.bounding_box()
                if box:
                    session["cursor"] = {
                        "x": float(box["x"] + (box["width"] / 2.0)),
                        "y": float(box["y"] + (box["height"] / 2.0)),
                    }
            except Exception:
                logger.exception("Failed to update cursor position after click on selector '%s'", selector)
            state = await self._capture_state(session_id, session)
            return {"success": True, "selector": selector, **state}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def type_text(self, session_id: str, *, selector: str, text: str, press_enter: bool = False) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        if not selector:
            return {"success": False, "error": "selector is required."}
        try:
            page = session["page"]
            await page.fill(selector, text, timeout=10000)
            if press_enter:
                await page.press(selector, "Enter")
            try:
                box = await page.locator(selector).first.bounding_box()
                if box:
                    session["cursor"] = {
                        "x": float(box["x"] + (box["width"] / 2.0)),
                        "y": float(box["y"] + (box["height"] / 2.0)),
                    }
            except Exception:
                logger.exception("Failed to update cursor position after type_text on selector '%s'", selector)
            state = await self._capture_state(session_id, session)
            return {"success": True, "selector": selector, **state}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def extract_text(self, session_id: str, *, selector: str = "body", max_chars: int = 12000) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        try:
            page = session["page"]
            text = await page.inner_text(selector or "body", timeout=10000)
            state = await self._capture_state(session_id, session)
            return {
                "success": True,
                **state,
                "text": (text or "")[:max_chars],
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def screenshot(self, session_id: str, *, full_page: bool = True) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        try:
            page = session["page"]
            raw = await page.screenshot(full_page=full_page)
            state = await self._capture_state(session_id, session)
            return {
                "success": True,
                **state,
                "image_base64": base64.b64encode(raw).decode("ascii"),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def get_state(self, session_id: str, *, include_links: bool = False, link_limit: int = 40) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        try:
            payload = await self._capture_state(session_id, session)
            if include_links:
                payload["links"] = await self._collect_links(session["page"], limit=link_limit)
            return {"success": True, **payload}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def list_links(self, session_id: str, *, limit: int = 40) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        try:
            payload = await self._capture_state(session_id, session)
            links = await self._collect_links(session["page"], limit=limit)
            return {"success": True, **payload, "links": links}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def cursor_move(
        self,
        session_id: str,
        *,
        x: float,
        y: float,
        steps: int = 1,
    ) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        try:
            page = session["page"]
            state = await self._capture_state(session_id, session)
            viewport = state.get("viewport") or {"width": 1280, "height": 720}
            width = float(viewport.get("width", 1280) or 1280)
            height = float(viewport.get("height", 720) or 720)
            final_x = self._clamp(float(x), 0.0, max(0.0, width - 1.0))
            final_y = self._clamp(float(y), 0.0, max(0.0, height - 1.0))
            await page.mouse.move(final_x, final_y, steps=max(1, int(steps)))
            session["cursor"] = {"x": final_x, "y": final_y}
            payload = await self._capture_state(session_id, session)
            return {"success": True, **payload}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def cursor_click(
        self,
        session_id: str,
        *,
        x: float | None = None,
        y: float | None = None,
        button: str = "left",
        click_count: int = 1,
        delay_ms: int = 0,
    ) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        try:
            page = session["page"]
            state = await self._capture_state(session_id, session)
            cursor = state.get("cursor") or {"x": 0.0, "y": 0.0}
            target_x = float(cursor.get("x", 0.0) if x is None else x)
            target_y = float(cursor.get("y", 0.0) if y is None else y)
            move_result = await self.cursor_move(session_id, x=target_x, y=target_y, steps=1)
            if not move_result.get("success"):
                return move_result
            await page.mouse.click(
                float(move_result["cursor"]["x"]),
                float(move_result["cursor"]["y"]),
                button=button if button in {"left", "right", "middle"} else "left",
                click_count=max(1, int(click_count)),
                delay=max(0, int(delay_ms)),
            )
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=3000)
            except Exception:
                logger.exception("Timed out or failed waiting for domcontentloaded after cursor_click")
            payload = await self._capture_state(session_id, session)
            return {
                "success": True,
                "button": button,
                "click_count": max(1, int(click_count)),
                **payload,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def cursor_hover(
        self,
        session_id: str,
        *,
        x: float | None = None,
        y: float | None = None,
        selector: str = "",
    ) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        try:
            page = session["page"]
            if selector:
                await page.hover(selector, timeout=10000)
                try:
                    box = await page.locator(selector).first.bounding_box()
                    if box:
                        session["cursor"] = {
                            "x": float(box["x"] + (box["width"] / 2.0)),
                            "y": float(box["y"] + (box["height"] / 2.0)),
                        }
                except Exception:
                    logger.exception("Failed to update cursor position after cursor_hover on selector '%s'", selector)
            elif x is not None and y is not None:
                moved = await self.cursor_move(session_id, x=float(x), y=float(y), steps=1)
                if not moved.get("success"):
                    return moved
            else:
                return {"success": False, "error": "selector or x/y is required."}
            payload = await self._capture_state(session_id, session)
            return {"success": True, **payload}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def cursor_scroll(
        self,
        session_id: str,
        *,
        dx: float = 0.0,
        dy: float = 600.0,
        x: float | None = None,
        y: float | None = None,
    ) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        try:
            page = session["page"]
            if x is not None and y is not None:
                moved = await self.cursor_move(session_id, x=float(x), y=float(y), steps=1)
                if not moved.get("success"):
                    return moved
            await page.mouse.wheel(float(dx), float(dy))
            await asyncio.sleep(0.05)
            payload = await self._capture_state(session_id, session)
            return {"success": True, "dx": float(dx), "dy": float(dy), **payload}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def close_session(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        try:
            await session["context"].close()
        except Exception:
            logger.exception("Failed to close browser context for session '%s'", session_id)
        try:
            await session["browser"].close()
        except Exception:
            logger.exception("Failed to close browser for session '%s'", session_id)
        try:
            await session["playwright"].stop()
        except Exception:
            logger.exception("Failed to stop playwright for session '%s'", session_id)
        return {"success": True, "session_id": session_id}

    async def close_all(self) -> dict[str, Any]:
        session_ids = list(self._sessions.keys())
        closed = 0
        for session_id in session_ids:
            result = await self.close_session(session_id)
            if result.get("success"):
                closed += 1
        return {"success": True, "closed": closed}
