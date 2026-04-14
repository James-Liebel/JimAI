"""AI-driven browser agent loop.

Takes a natural-language goal, opens a Playwright browser session, and loops:
  screenshot → vision model → JSON action → execute → repeat

Streams step events as async dicts so the caller can forward them over SSE.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncGenerator

from models import ollama_client

logger = logging.getLogger(__name__)

MAX_STEPS_DEFAULT = 20
SCREENSHOT_MODEL = "qwen2.5vl:7b"

_ACTION_SYSTEM = """\
You are a browser agent. You see a viewport screenshot of a web page.
Your job: take the single best next action to achieve the user's goal.

Respond ONLY with a valid JSON object — no markdown, no explanation:
{
  "thought": "<one sentence: what you see and why this action>",
  "action": "click" | "type" | "navigate" | "scroll" | "wait" | "done",
  "x": <integer pixel x for click>,
  "y": <integer pixel y for click>,
  "text": "<text to type>",
  "selector": "<CSS selector for the input to type into>",
  "url": "<full URL for navigate>",
  "dy": <integer pixels to scroll — positive = down, negative = up>,
  "result": "<summary of what was achieved — only for done>"
}

Include only the keys relevant to your chosen action.
Rules:
- Use pixel coordinates (x, y) relative to the screenshot for click
- For type: identify the input by its CSS selector; most inputs are: input, textarea, [contenteditable]
- Use navigate when a direct URL is faster than clicking
- Use scroll when content is off-screen
- Use done when the goal is fully achieved or definitively cannot be achieved
- Never repeat a failed action more than once — try a different approach
"""


def _parse_action(raw: str) -> dict[str, Any]:
    """Extract JSON from model output, tolerating markdown fences."""
    text = str(raw or "").strip()
    # Strip ```json ... ``` fences
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        text = fenced.group(1).strip()
    # Find first { ... } block
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        text = brace.group(0)
    try:
        return dict(json.loads(text))
    except Exception:
        return {"action": "wait", "thought": f"Could not parse model output: {raw[:120]}"}


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
      {"type": "done",    "step": N, "result": ..., "url": ...}
      {"type": "stopped", "reason": ...}
    """
    goal = str(goal or "").strip()
    start_url = str(start_url or "").strip()
    if not start_url.startswith("http"):
        start_url = f"https://{start_url}" if start_url else "about:blank"

    # Open session
    opened = await browser_manager.open_session(url=start_url, headless=headless)
    if not opened.get("success"):
        yield {"type": "stopped", "reason": opened.get("error", "Failed to open browser.")}
        return

    session_id: str = opened["session_id"]
    yield {"type": "opened", "session_id": session_id, "url": opened.get("url", start_url)}

    action_history: list[str] = []

    try:
        for step in range(1, max_steps + 1):
            # Capture screenshot
            shot = await browser_manager.screenshot(session_id, full_page=False)
            if not shot.get("success"):
                yield {"type": "error", "step": step, "error": shot.get("error", "Screenshot failed.")}
                break
            b64_img: str = shot["image_base64"]
            current_url: str = shot.get("url", "")

            # Build prompt
            history_str = ""
            if action_history:
                history_str = "\nPrevious actions:\n" + "\n".join(
                    f"  {i+1}. {a}" for i, a in enumerate(action_history[-6:])
                )
            user_prompt = (
                f"Goal: {goal}\n"
                f"Current URL: {current_url}{history_str}\n\n"
                "What is your next action? Respond with JSON only."
            )

            messages = [
                {"role": "system", "content": _ACTION_SYSTEM},
                {"role": "user", "content": user_prompt, "images": [b64_img]},
            ]

            # Ask vision model
            try:
                raw = await ollama_client.chat_full(
                    model=SCREENSHOT_MODEL,
                    messages=messages,
                    temperature=0.1,
                    num_ctx=4096,
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

            # Record history
            action_history.append(f"{action_type}: {thought}")

            # Execute
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

            elif action_type == "click":
                x = action.get("x")
                y = action.get("y")
                if x is not None and y is not None:
                    result = await browser_manager.cursor_click(session_id, x=float(x), y=float(y))
                    if not result.get("success"):
                        yield {"type": "error", "step": step, "error": result.get("error", "Click failed.")}

            elif action_type == "type":
                selector = str(action.get("selector", "input, textarea, [contenteditable]")).strip()
                text = str(action.get("text", "")).strip()
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

            elif action_type == "wait":
                import asyncio
                await asyncio.sleep(1.5)

        else:
            yield {"type": "stopped", "reason": f"Reached max steps ({max_steps})."}

    finally:
        try:
            await browser_manager.close_session(session_id)
        except Exception:
            pass


_ACTION_SYSTEM_EXPORTED = _ACTION_SYSTEM
