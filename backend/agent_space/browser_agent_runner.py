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

# Atlas chat panel — CPU-only inference, no GPU heat.
# Both tiers use qwen2.5-coder:3b (smallest installed model) with num_gpu=0 so
# the browser agent never competes with the main chat models for VRAM.
BROWSER_EXECUTOR_MODEL = "qwen2.5-coder:3b"
BROWSER_PLANNER_MODEL = "qwen2.5-coder:3b"
BROWSER_NUM_GPU = 0        # CPU-only: no VRAM, no heat
BROWSER_KEEP_ALIVE = "3m"  # unload quickly when idle

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
    # Strip <think>…</think> blocks produced by qwen3/deepseek reasoning models
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        text = fenced.group(1).strip()
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        text = brace.group(0)
    try:
        return dict(json.loads(text))
    except Exception:
        return {"action": "talk", "thought": f"Could not parse model output: {raw[:120]}", "response": "I had trouble understanding that page. Could you describe what you see or try again?"}


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


_EXECUTOR_SYSTEM = """\
Browser automation executor. Output ONE action as JSON — no markdown, no extra text.

Format: {"thought":"one sentence","action":"ACTION","params":{...},"response":"plain English"}

Actions:
  navigate         {"url":"https://..."}
  click_selector   {"selector":"css"}
  trigger_autofill {"selector":"css"}  ← use this for email/password fields to fill from saved passwords
  type             {"selector":"css","text":"value"}
  type_and_submit  {"selector":"css","text":"value"}
  press_key        {"key":"Enter"}
  scroll           {"dy":400}
  js               {"code":"js expression"}
  wait             {}
  done             {}

Key selectors:
  Google email input  : input[name="identifier"]
  Google email Next   : #identifierNext
  Google password     : input[name="Passwd"],input[type="password"]
  Google password Next: #passwordNext
  Google search       : textarea[name="q"],input[name="q"]
  Generic submit      : button[type="submit"]

Login rule: ALWAYS use trigger_autofill on email and password fields — the browser has saved credentials from the user's Google account. Only fall back to type if autofill finds nothing."""

_PLANNER_SYSTEM = """\
You are a browser agent embedded in an AI desktop app (JimAI). You control a real Chrome browser \
running inside Electron. The user can also browse manually alongside you.

Given the current page state and the user's instruction, output ONE action as valid JSON.
Do NOT output any markdown, code fences, comments, or explanation — ONLY the JSON object.

Required keys: "thought", "action", "params", "response"

Actions and their params objects:
  navigate         -> {"url": "https://..."}
  click_selector   -> {"selector": "css_selector"}
  trigger_autofill -> {"selector": "css_selector"}   ← preferred for email/password fields
  type             -> {"selector": "css_selector", "text": "text to type"}
  type_and_submit  -> {"selector": "css_selector", "text": "text to type"}
  press_key        -> {"key": "Enter"}
  scroll           -> {"dy": 400}
  js               -> {"code": "javascript expression"}
  wait             -> {}
  talk             -> {}
  done             -> {}

CSS selector reference (prefer specific):
  Google login email:     input[type="email"], input[name="identifier"]
  Google login password:  input[type="password"], input[name="Passwd"]
  Google "Next" button:   #identifierNext, #passwordNext, button[jsname="LgbsSe"]
  Google search box:      textarea[name="q"], input[name="q"]
  AP Classroom login:     navigate to classroom.google.com then sign in with Google
  Generic submit:         button[type="submit"], input[type="submit"]
  Generic search:         input[type="search"], input[aria-label*="earch" i]

Rules:
- Use "talk" only for greetings or clarifications requiring no browser action.
- Use "wait" when you need the page to finish loading.
- Use "done" when the user's goal is fully achieved.
- For login forms: use trigger_autofill on the email field, then click_selector #identifierNext, then trigger_autofill on the password field, then click_selector #passwordNext. The user's Google account has saved passwords — always try autofill first.
- Prefer navigate over clicking links when you know the URL.
- Always fill "response" with a plain-English description of what you are doing."""


async def chat_browser_step(
    message: str,
    url: str,
    title: str,
    page_text: str,
    history: list[dict],
) -> dict:
    """Single-step browser agent for the Atlas chat panel.

    The frontend handles the execution loop; this function only generates the next action.
    """
    # Model selection: planner for first step + error recovery, executor for everything else.
    # Planner (qwen3:8b) reasons about the goal and recovers from failures.
    # Executor (qwen2.5-coder:7b) is fast and accurate for mechanical click/type/navigate steps.
    user_turns = [h for h in history if str(h.get("role", "")) == "user"]
    recent_contents = " ".join(str(h.get("content", "")) for h in history[-4:]).lower()
    is_first_step = len(user_turns) <= 1
    is_stuck = recent_contents.count("could not parse") >= 1 or recent_contents.count("error") >= 2

    use_planner = is_first_step or is_stuck
    model = BROWSER_PLANNER_MODEL if use_planner else BROWSER_EXECUTOR_MODEL
    system_prompt = _PLANNER_SYSTEM if use_planner else _EXECUTOR_SYSTEM
    num_ctx = 8192 if use_planner else 4096
    num_predict = 512 if use_planner else 256
    num_batch = 1024 if use_planner else 512

    page_block = (
        f"Current URL: {url or '(unknown)'}\n"
        f"Page title:  {title or '(unknown)'}\n\n"
        f"Page content:\n{(page_text or '(empty)').strip()[:3000 if not use_planner else 4000]}"
    )

    user_prompt = (
        f"Page state:\n{page_block}\n\n"
        f"User instruction: {message}\n\n"
        "Output JSON only:"
    )

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for turn in history[-6:]:
        role = str(turn.get("role", "user"))
        content = str(turn.get("content", "")).strip()
        if content and role in ("user", "agent", "assistant"):
            messages.append({"role": "user" if role == "user" else "assistant", "content": content})
    messages.append({"role": "user", "content": user_prompt})

    raw = await ollama_client.chat_full(
        model=model,
        messages=messages,
        temperature=0.1 if not use_planner else 0.15,
        num_ctx=num_ctx,
        num_predict=num_predict,
        num_batch=num_batch,
        repeat_penalty=1.05,
        think=False,
        num_gpu=BROWSER_NUM_GPU,
        keep_alive=BROWSER_KEEP_ALIVE,
    )

    parsed = _parse_action(raw)
    if "response" not in parsed:
        parsed["response"] = parsed.get("thought", raw.strip()[:300])
    if "params" not in parsed:
        parsed["params"] = {}
    return parsed
