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

    async def open_session(
        self,
        *,
        url: str = "",
        headless: bool = True,
        viewport_width: int | None = None,
        viewport_height: int | None = None,
        user_agent: str = "",
        locale: str = "",
        timezone_id: str = "",
        ignore_https_errors: bool = False,
        slow_mo_ms: int = 0,
    ) -> dict[str, Any]:
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
            launch_kw: dict[str, Any] = {"headless": headless}
            sm = max(0, min(int(slow_mo_ms or 0), 2000))
            if sm > 0:
                launch_kw["slow_mo"] = sm
            browser = await playwright.chromium.launch(**launch_kw)
            ctx_kw: dict[str, Any] = {}
            vw = int(viewport_width) if viewport_width is not None else None
            vh = int(viewport_height) if viewport_height is not None else None
            if vw is not None and vh is not None:
                ctx_kw["viewport"] = {"width": max(320, min(vw, 3840)), "height": max(240, min(vh, 2160))}
            ua = str(user_agent or "").strip()
            if ua:
                ctx_kw["user_agent"] = ua
            loc = str(locale or "").strip()
            if loc:
                ctx_kw["locale"] = loc
            tz = str(timezone_id or "").strip()
            if tz:
                ctx_kw["timezone_id"] = tz
            if ignore_https_errors:
                ctx_kw["ignore_https_errors"] = True
            context = await browser.new_context(**ctx_kw)
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

    async def open_atlas_session(
        self,
        *,
        url: str = "https://www.google.com",
        profile_dir: str = "",
    ) -> dict[str, Any]:
        """Launch a persistent Chrome session with a saved profile (cookies, logins intact).

        Uses the real installed Chrome when available (channel='chrome'), falling back
        to Playwright's bundled Chromium. The profile_dir is preserved between calls so
        Google/other logins survive restarts.
        """
        can_spawn, spawn_error = await self._can_spawn_subprocess()
        if not can_spawn:
            return {"success": False, "error": f"Browser launch unavailable: {spawn_error}"}
        try:
            from playwright.async_api import async_playwright
        except Exception:
            return {"success": False, "error": "playwright is not installed."}

        if not profile_dir:
            from .paths import DATA_ROOT
            profile_dir = str(DATA_ROOT / "browser_profile")

        import pathlib
        pathlib.Path(profile_dir).mkdir(parents=True, exist_ok=True)

        playwright = None
        context = None
        try:
            playwright = await async_playwright().start()
            launch_kw: dict[str, Any] = {
                "headless": False,
                "viewport": {"width": 1280, "height": 800},
                "args": ["--no-first-run", "--no-default-browser-check"],
            }
            # Try real Chrome first; fall back to bundled Chromium
            try:
                context = await playwright.chromium.launch_persistent_context(
                    profile_dir,
                    channel="chrome",
                    **launch_kw,
                )
            except Exception:
                context = await playwright.chromium.launch_persistent_context(
                    profile_dir,
                    **launch_kw,
                )

            pages = context.pages
            page = pages[0] if pages else await context.new_page()
            if url and url != "about:blank":
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    pass

            viewport = page.viewport_size or {"width": 1280, "height": 800}
            session_id = str(uuid.uuid4())
            self._sessions[session_id] = {
                "playwright": playwright,
                "browser": None,       # persistent context has no separate Browser object
                "context": context,
                "page": page,
                "created_at": time.time(),
                "headless": False,
                "persistent": True,
                "profile_dir": profile_dir,
                "cursor": {
                    "x": float((viewport.get("width", 1280) or 1280) / 2.0),
                    "y": float((viewport.get("height", 800) or 800) / 2.0),
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
                "headless": False,
                "persistent": True,
                "profile_dir": profile_dir,
            }
        except Exception as exc:
            try:
                if context:
                    await context.close()
            except Exception:
                pass
            try:
                if playwright:
                    await playwright.stop()
            except Exception:
                pass
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

    async def type_text(
        self,
        session_id: str,
        *,
        selector: str,
        text: str,
        press_enter: bool = False,
        clear_first: bool = True,
    ) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        if not selector:
            return {"success": False, "error": "selector is required."}
        try:
            page = session["page"]
            loc = page.locator(selector).first
            if clear_first:
                await loc.fill(text, timeout=10000)
            else:
                await loc.press_sequentially(text, delay=15, timeout=15000)
            if press_enter:
                await loc.press("Enter")
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

    async def scroll_page(
        self,
        session_id: str,
        *,
        delta_x: float = 0.0,
        delta_y: float = 0.0,
        position: str = "",
    ) -> dict[str, Any]:
        """Programmatic window scroll (complements mouse-wheel browser_scroll)."""
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        try:
            page = session["page"]
            pos = str(position or "").strip().lower()
            if pos in {"top", "start"}:
                await page.evaluate("() => window.scrollTo(0, 0)")
            elif pos in {"bottom", "end"}:
                await page.evaluate(
                    """() => window.scrollTo(0, Math.max(0, document.documentElement.scrollHeight - window.innerHeight))"""
                )
            elif delta_x != 0.0 or delta_y != 0.0:
                await page.evaluate(
                    """([dx, dy]) => window.scrollBy(dx, dy)""",
                    [float(delta_x), float(delta_y)],
                )
            else:
                return {"success": False, "error": "Provide delta_x/delta_y or position top|bottom."}
            await asyncio.sleep(0.05)
            payload = await self._capture_state(session_id, session)
            return {"success": True, "delta_x": float(delta_x), "delta_y": float(delta_y), "position": pos, **payload}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def scroll_into_view(self, session_id: str, *, selector: str) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        if not str(selector or "").strip():
            return {"success": False, "error": "selector is required."}
        try:
            page = session["page"]
            await page.locator(selector).first.scroll_into_view_if_needed(timeout=15000)
            payload = await self._capture_state(session_id, session)
            return {"success": True, "selector": selector, **payload}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def select_option(
        self,
        session_id: str,
        *,
        selector: str,
        value: str = "",
        label: str = "",
    ) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        if not selector:
            return {"success": False, "error": "selector is required."}
        val = str(value or "").strip()
        lab = str(label or "").strip()
        if not val and not lab:
            return {"success": False, "error": "value or label is required."}
        try:
            page = session["page"]
            loc = page.locator(selector).first
            if val:
                await loc.select_option(value=val, timeout=10000)
            else:
                await loc.select_option(label=lab, timeout=10000)
            payload = await self._capture_state(session_id, session)
            return {"success": True, "selector": selector, **payload}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def set_checked(
        self,
        session_id: str,
        *,
        selector: str,
        checked: bool = True,
    ) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        if not selector:
            return {"success": False, "error": "selector is required."}
        try:
            page = session["page"]
            await page.locator(selector).first.set_checked(bool(checked), timeout=10000)
            payload = await self._capture_state(session_id, session)
            return {"success": True, "selector": selector, "checked": bool(checked), **payload}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def press_key(
        self,
        session_id: str,
        *,
        key: str,
        selector: str = "",
    ) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        k = str(key or "").strip()
        if not k:
            return {"success": False, "error": "key is required (Playwright name e.g. Tab, Enter, Escape)."}
        try:
            page = session["page"]
            sel = str(selector or "").strip()
            if sel:
                await page.locator(sel).first.focus(timeout=10000)
            await page.keyboard.press(k)
            payload = await self._capture_state(session_id, session)
            return {"success": True, "key": k, **payload}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def wait_for(
        self,
        session_id: str,
        *,
        selector: str,
        state: str = "visible",
        timeout_ms: int = 30000,
    ) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        if not selector:
            return {"success": False, "error": "selector is required."}
        st = str(state or "visible").strip().lower()
        if st not in {"attached", "detached", "visible", "hidden"}:
            st = "visible"
        try:
            page = session["page"]
            await page.wait_for_selector(selector, state=st, timeout=max(1000, min(int(timeout_ms), 120000)))
            payload = await self._capture_state(session_id, session)
            return {"success": True, "selector": selector, "state": st, **payload}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def list_interactive(self, session_id: str, *, limit: int = 80) -> dict[str, Any]:
        """Snapshot inputs/buttons for form-filling agents (selectors prefer #id or [name=])."""
        session = self._sessions.get(session_id)
        if session is None:
            return {"success": False, "error": f"Unknown session_id '{session_id}'."}
        lim = max(1, min(int(limit), 200))
        try:
            page = session["page"]
            rows = await page.evaluate(
                """(limit) => {
                    const out = [];
                    const selectorFor = (el) => {
                        if (el.id) {
                            return '#' + (window.CSS && CSS.escape ? CSS.escape(el.id) : el.id.replace(/([^a-zA-Z0-9_-])/g, '\\\\$1'));
                        }
                        const nm = el.getAttribute('name');
                        if (nm) return el.tagName.toLowerCase() + '[name=' + JSON.stringify(nm) + ']';
                        return '';
                    };
                    const nodes = Array.from(document.querySelectorAll('input, select, textarea, button'));
                    for (let i = 0; i < nodes.length && out.length < limit; i++) {
                        const el = nodes[i];
                        const type = (el.type || el.tagName || '').toLowerCase();
                        if (type === 'hidden') continue;
                        const rect = el.getBoundingClientRect();
                        const visible = rect.width > 0 && rect.height > 0;
                        const sel = selectorFor(el);
                        if (!sel) continue;
                        let label = '';
                        if (el.id) {
                            const lbl = document.querySelector('label[for=' + JSON.stringify(el.id) + ']');
                            if (lbl) label = (lbl.innerText || lbl.textContent || '').trim().slice(0, 240);
                        }
                        out.push({
                            tag: el.tagName.toLowerCase(),
                            type: type,
                            selector: sel,
                            name: el.getAttribute('name') || '',
                            id: el.id || '',
                            placeholder: (el.getAttribute('placeholder') || '').slice(0, 240),
                            label: label,
                            aria_label: (el.getAttribute('aria-label') || '').slice(0, 240),
                            required: !!el.required,
                            disabled: !!el.disabled,
                            visible: visible,
                        });
                    }
                    return out;
                }""",
                lim,
            )
            payload = await self._capture_state(session_id, session)
            fields = rows if isinstance(rows, list) else []
            return {"success": True, "fields": fields, "count": len(fields), **payload}
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
