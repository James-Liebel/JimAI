"""AI-driven browser agent loop — DOM-based, no vision model required.

Each step:
  extract page text + interactive elements → fast text model → JSON action → execute

Screenshots are still captured per step so the UI can show progress, but
the model never sees them. This is faster, cheaper, and more reliable than
asking a vision model to interpret pixel coordinates.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, AsyncGenerator

from models import ollama_client

logger = logging.getLogger(__name__)

MAX_STEPS_DEFAULT = 20
# Small, fast model — no vision needed
AGENT_MODEL = "qwen3:8b"

_ACTION_SYSTEM = """\
You are a browser automation agent. You receive the current page's URL, title, \
visible text, and a list of interactive elements (inputs, buttons, links).

Respond ONLY with a single valid JSON object — no markdown, no commentary:
{
  "thought": "<one sentence: what you see and why this action>",
  "action": "click_selector" | "click_link" | "type" | "navigate" | "scroll" | "press_key" | "wait" | "done",
  "selector": "<CSS selector — for click_selector or type>",
  "href": "<exact href from links list — for click_link>",
  "text": "<text to type — for type>",
  "press_enter": true,
  "url": "<full URL — for navigate>",
  "dy": <scroll pixels, positive=down — for scroll>,
  "key": "<Playwright key name e.g. Enter, Tab, Escape — for press_key>",
  "result": "<summary — only for done>"
}

Include only keys relevant to your action. Rules:
- Prefer click_selector over click_link when there is a clear selector
- For text input: fill the field then set press_enter=true if it is a search/form submit
- Use navigate when a direct URL is faster than clicking
- Use done when the goal is fully achieved or definitively cannot be achieved
- Keep thoughts to one sentence
"""


def _parse_action(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        text = fenced.group(1).strip()
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        text = brace.group(0)
    try:
        return dict(json.loads(text))
    except Exception:
        return {"action": "wait", "thought": f"Could not parse model output: {raw[:120]}"}


def _build_page_context(
    url: str,
    title: str,
    page_text: str,
    interactive: list[dict[str, Any]],
    links: list[dict[str, Any]],
) -> str:
    lines = [f"URL: {url}", f"Title: {title}", ""]

    if interactive:
        lines.append("Interactive elements:")
        for el in interactive[:30]:
            sel = el.get("selector", "")
            tag = el.get("tag", "")
            label = el.get("label") or el.get("placeholder") or el.get("name") or ""
            el_type = el.get("type", "")
            lines.append(f"  [{tag}/{el_type}] selector={sel!r}  label={label!r}")
        lines.append("")

    if links:
        lines.append("Links (first 20):")
        for lk in links[:20]:
            href = lk.get("href", "")
            text = lk.get("text", "")[:80]
            lines.append(f"  {text!r} → {href}")
        lines.append("")

    # Trim page text to avoid token overflow
    trimmed = (page_text or "")[:3000]
    if trimmed:
        lines.append("Page text:")
        lines.append(trimmed)

    return "\n".join(lines)


async def run_browser_agent(
    goal: str,
    start_url: str,
    *,
    browser_manager: Any,
    max_steps: int = MAX_STEPS_DEFAULT,
    headless: bool = False,
) -> AsyncGenerator[dict[str, Any], None]:
    """Async generator — yields step dicts for SSE forwarding.

    Event types:
      {"type": "opened",  "session_id": ..., "url": ...}
      {"type": "step",    "step": N, "thought": ..., "action": ..., "screenshot": <b64>}
      {"type": "error",   "step": N, "error": ...}
      {"type": "done",    "step": N, "result": ..., "url": ..., "screenshot": <b64>}
      {"type": "stopped", "reason": ...}
    """
    goal = str(goal or "").strip()
    start_url = str(start_url or "").strip()
    if not start_url.startswith("http"):
        start_url = f"https://{start_url}" if start_url else "about:blank"

    opened = await browser_manager.open_session(url=start_url, headless=headless)
    if not opened.get("success"):
        yield {"type": "stopped", "reason": opened.get("error", "Failed to open browser.")}
        return

    session_id: str = opened["session_id"]
    yield {"type": "opened", "session_id": session_id, "url": opened.get("url", start_url)}

    action_history: list[str] = []

    try:
        for step in range(1, max_steps + 1):
            # Capture screenshot for the UI (not fed to model)
            shot = await browser_manager.screenshot(session_id, full_page=False)
            b64_img: str = shot.get("image_base64", "") if shot.get("success") else ""
            current_url: str = shot.get("url", "") if shot.get("success") else ""

            # Extract page context for the model
            state_data = await browser_manager.get_state(session_id, include_links=True, link_limit=25)
            text_data = await browser_manager.extract_text(session_id, selector="body", max_chars=3000)
            interactive_data = await browser_manager.list_interactive(session_id, limit=30)

            page_text = text_data.get("text", "") if text_data.get("success") else ""
            links = list(state_data.get("links") or []) if state_data.get("success") else []
            interactive = list(interactive_data.get("fields") or []) if interactive_data.get("success") else []
            title = state_data.get("title", "") if state_data.get("success") else ""
            current_url = current_url or (state_data.get("url", "") if state_data.get("success") else "")

            page_context = _build_page_context(current_url, title, page_text, interactive, links)

            history_str = ""
            if action_history:
                history_str = "\nPrevious actions:\n" + "\n".join(
                    f"  {i+1}. {a}" for i, a in enumerate(action_history[-6:])
                )

            user_prompt = (
                f"Goal: {goal}{history_str}\n\n"
                f"{page_context}\n\n"
                "What is your next action? Respond with JSON only."
            )

            messages = [
                {"role": "system", "content": _ACTION_SYSTEM},
                {"role": "user", "content": user_prompt},
            ]

            try:
                raw = await ollama_client.chat_full(
                    model=AGENT_MODEL,
                    messages=messages,
                    temperature=0.1,
                    num_ctx=8192,
                    think=False,
                )
                if not raw.strip():
                    raw = '{"action": "wait", "thought": "Empty model response."}'
            except Exception as exc:
                yield {"type": "error", "step": step, "error": str(exc)}
                break

            action = _parse_action(raw)
            action_type = str(action.get("action", "wait")).lower()
            thought = str(action.get("thought", ""))

            yield {
                "type": "step",
                "step": step,
                "thought": thought,
                "action": action_type,
                "action_detail": action,
                "screenshot": b64_img,
                "url": current_url,
            }

            action_history.append(f"{action_type}: {thought}")

            if action_type == "done":
                yield {
                    "type": "done",
                    "step": step,
                    "result": str(action.get("result", "Goal complete.")),
                    "url": current_url,
                    "screenshot": b64_img,
                }
                return

            elif action_type == "navigate":
                nav_url = str(action.get("url", "")).strip()
                if nav_url:
                    result = await browser_manager.navigate(session_id, nav_url)
                    if not result.get("success"):
                        yield {"type": "error", "step": step, "error": result.get("error", "Navigate failed.")}

            elif action_type == "click_selector":
                selector = str(action.get("selector", "")).strip()
                if selector:
                    result = await browser_manager.click(session_id, selector)
                    if not result.get("success"):
                        yield {"type": "error", "step": step, "error": result.get("error", "Click failed.")}

            elif action_type == "click_link":
                href = str(action.get("href", "")).strip()
                if href:
                    if href.startswith("http"):
                        result = await browser_manager.navigate(session_id, href)
                    else:
                        result = await browser_manager.click(session_id, f'a[href="{href}"]')
                    if not result.get("success"):
                        yield {"type": "error", "step": step, "error": result.get("error", "Link click failed.")}

            elif action_type == "type":
                selector = str(action.get("selector", "input, textarea, [contenteditable]")).strip()
                text = str(action.get("text", ""))
                press_enter = bool(action.get("press_enter", False))
                if text:
                    result = await browser_manager.type_text(
                        session_id,
                        selector=selector,
                        text=text,
                        press_enter=press_enter,
                        clear_first=True,
                    )
                    if not result.get("success"):
                        yield {"type": "error", "step": step, "error": result.get("error", "Type failed.")}

            elif action_type == "scroll":
                dy = float(action.get("dy", 600))
                result = await browser_manager.scroll_page(session_id, delta_y=dy)
                if not result.get("success"):
                    yield {"type": "error", "step": step, "error": result.get("error", "Scroll failed.")}

            elif action_type == "press_key":
                key = str(action.get("key", "")).strip()
                if key:
                    result = await browser_manager.press_key(session_id, key=key)
                    if not result.get("success"):
                        yield {"type": "error", "step": step, "error": result.get("error", "Key press failed.")}

            elif action_type == "wait":
                await asyncio.sleep(1.5)

        else:
            yield {"type": "stopped", "reason": f"Reached max steps ({max_steps})."}

    finally:
        try:
            await browser_manager.close_session(session_id)
        except Exception:
            logger.warning("browser_agent: failed to close session %s", session_id, exc_info=True)
