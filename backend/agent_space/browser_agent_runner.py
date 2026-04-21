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
import urllib.parse
from typing import Any, AsyncGenerator

from models import ollama_client

logger = logging.getLogger(__name__)

MAX_STEPS_DEFAULT = 20
# Small, fast model — no vision needed
AGENT_MODEL = "qwen3:8b"

# Atlas chat panel — two-tier model selection.
# Executor: qwen2.5-coder:3b — fast mechanical actions (click/type/navigate).
# Planner:  qwen3:8b — first step + error recovery, better world knowledge.
# num_gpu=None lets Ollama split layers across GPU+CPU automatically (balanced load).
# OLLAMA_MAX_LOADED_MODELS=1 handles VRAM contention between browser agent and chat models.
BROWSER_EXECUTOR_MODEL = "qwen2.5-coder:3b"
BROWSER_PLANNER_MODEL = "qwen3:8b"
BROWSER_NUM_GPU: int | None = None  # balanced GPU+CPU — Ollama decides layer split
BROWSER_KEEP_ALIVE = "3m"           # unload quickly when idle

# Known service → URL lookup. Injected into the prompt so the model never guesses.
_SERVICE_URLS: dict[str, str] = {
    "ap classroom": "https://myap.collegeboard.org",
    "college board": "https://www.collegeboard.org",
    "google classroom": "https://classroom.google.com",
    "canvas": "https://canvas.instructure.com",
    "schoology": "https://app.schoology.com",
    "blackboard": "https://blackboard.com",
    "khan academy": "https://www.khanacademy.org",
    "duolingo": "https://www.duolingo.com",
    "quizlet": "https://quizlet.com",
    "chegg": "https://www.chegg.com",
    "turnitin": "https://www.turnitin.com",
}

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


def _parse_action_strict(raw: str) -> dict[str, Any] | None:
    """Best-effort JSON parsing for atlas browser chat actions."""
    text = str(raw or "").strip()
    if not text:
        return None

    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        text = fenced.group(1).strip()

    candidates: list[str] = [text]
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        candidates.append(brace.group(0))

    for cand in candidates:
        fixed = (
            cand.replace("“", '"')
            .replace("”", '"')
            .replace("’", "'")
            .replace("\u00a0", " ")
            .strip()
        )
        # Remove trailing commas before } or ] which models often emit.
        fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
        try:
            parsed = json.loads(fixed)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return None


def _normalize_chat_action(
    parsed: dict[str, Any] | None,
    *,
    message: str,
    url: str,
    page_text: str,
) -> dict[str, Any]:
    """Normalize model output into a safe single browser action."""
    safe: dict[str, Any] = dict(parsed or {})
    action = str(safe.get("action", "wait")).strip().lower()
    response = str(safe.get("response", "")).strip()
    thought = str(safe.get("thought", "")).strip()
    params_obj = safe.get("params")
    params: dict[str, Any] = params_obj if isinstance(params_obj, dict) else {}

    allowed = {
        "navigate",
        "click_xy",
        "type_xy",
        "click_selector",
        "trigger_autofill",
        "type",
        "type_and_submit",
        "press_key",
        "scroll",
        "js",
        "wait",
        "talk",
        "done",
    }
    if action not in allowed:
        action = "wait"

    url_l = (url or "").lower()

    # Convert Google search typing into a direct search URL — faster and avoids UI interaction.
    if action in {"type", "type_and_submit"}:
        sel = str(params.get("selector", "")).lower()
        text = str(params.get("text", "")).strip()
        if text and ('name="q"' in sel or "name='q'" in sel or sel in {"textarea", "input"}):
            action = "navigate"
            params = {"url": f"https://www.google.com/search?q={urllib.parse.quote_plus(text)}"}
            if not response:
                response = f'Searching Google for "{text}".'

    # If we're already on Google results, repeated search submissions often loop.
    # Nudge toward opening a result instead of searching again.
    if action == "type_and_submit" and "google." in url_l and "/search" in url_l:
        action = "click_selector"
        params = {"selector": "a h3"}
        if not response:
            response = "Opening the top search result."

    # Fill in minimal defaults so frontend executor always has valid params.
    if action == "click_xy":
        params.setdefault("x", 0)
        params.setdefault("y", 0)
    elif action == "type_xy":
        params.setdefault("x", 0)
        params.setdefault("y", 0)
        params.setdefault("text", "")
    elif action in {"type", "type_and_submit"}:
        params.setdefault("selector", 'textarea[name="q"],input[name="q"]')
        params.setdefault("text", "")
    elif action == "click_selector":
        params.setdefault("selector", "button[type='submit']")
    elif action == "navigate":
        params.setdefault("url", "")
    elif action == "press_key":
        params.setdefault("key", "Enter")
    elif action == "scroll":
        params.setdefault("dy", 400)

    # If parse failed, do not expose raw parser error to users; recover gracefully.
    if parsed is None:
        action = "wait"
        params = {}
        if not thought:
            thought = "Model output was malformed; waiting and retrying."
        if not response:
            response = "Let me retry that step."

    if not response:
        response = thought or "Working on it."
    if not thought:
        thought = response

    # Prevent mega-responses from polluting turn history.
    response = response[:260]
    thought = thought[:260]

    return {
        "thought": thought,
        "action": action,
        "params": params,
        "response": response,
    }


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

The page context includes a "Visible elements" list showing every clickable/typeable element \
with its screen coordinates: tag (x,y) "label". Use these coordinates to interact — they work \
on every site, including React/Angular SPAs where CSS selectors break.

Format: {"thought":"one sentence","action":"ACTION","params":{...},"response":"plain English"}

Actions (prefer top ones):
  navigate    {"url":"https://..."}
  click_xy    {"x":300,"y":450}                         ← click element by screen coordinates
  type_xy     {"x":300,"y":450,"text":"value"}           ← focus field at coords, then type
  press_key   {"key":"Enter"}                            ← key to focused element (Enter, Tab, Escape)
  scroll      {"dy":400}                                 ← positive=down, negative=up
  wait        {}
  done        {}
  click_selector  {"selector":"css"}                    ← fallback when no coords available
  trigger_autofill {"selector":"css"}                   ← trigger saved-password autofill popup

Rules:
- ALWAYS use click_xy and type_xy — read the (x,y) from the Visible elements list.
- To search Google: navigate {"url":"https://www.google.com/search?q=your+query"} — never type in search box.
- After clicking a button that loads a new page, use wait to let it settle.
- For login forms: type_xy the email field, click_xy the Next/Continue button, type_xy the password, click_xy Sign In.
- Never guess what element to click — read the Visible elements list for exact coordinates."""

_PLANNER_SYSTEM = """\
You are a browser agent embedded in an AI desktop app (JimAI). You control a real Chrome browser \
running inside Electron. The user can browse manually alongside you.

The page context includes a "Visible elements" section listing every interactive element currently \
on screen with its coordinates: tag (x,y) "label". These coordinates are exact pixel positions — \
use them to click and type. This works on every site regardless of framework.

First understand what the user wants. Then output ONE action as valid JSON.
Do NOT output markdown, code fences, or explanation — ONLY the JSON object.

Required keys: "thought", "action", "params", "response"

Actions (prefer top ones):
  navigate         -> {"url": "https://..."}
  click_xy         -> {"x": 300, "y": 450}                       ← click by screen coordinates
  type_xy          -> {"x": 300, "y": 450, "text": "value"}      ← focus field at coords, then type
  press_key        -> {"key": "Enter"}                            ← key sent to focused element
  scroll           -> {"dy": 400}                                 ← positive=down, negative=up
  wait             -> {}
  talk             -> {}
  done             -> {}
  click_selector   -> {"selector": "css"}                         ← fallback only
  trigger_autofill -> {"selector": "css"}                         ← trigger saved-password autofill

Rules:
- Always look at the Visible elements list to find what to click — read the (x,y) coordinates and use click_xy / type_xy.
- To search Google: navigate {"url": "https://www.google.com/search?q=your+query"} — never type in the search box.
- If you don't know a site's URL, navigate to a Google search URL for it.
- For login forms: type_xy the email, click_xy Next, type_xy the password, click_xy Sign In.
- After clicking a button that navigates or opens content, use wait to let the page load.
- Use "talk" only for greetings or questions needing no browser action.
- Use "done" when the goal is fully achieved.
- Never repeat the same action+params twice in a row — if stuck, scroll to find more elements or wait.
- Always fill "response" with plain English describing what you are doing."""


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
    recent_contents = " ".join(str(h.get("content", "")) for h in history[-6:]).lower()

    # Detect repeated actions — same [action] tag 3+ times in last 5 agent turns
    agent_turns = [h for h in history if str(h.get("role", "")) in ("agent", "assistant")]
    recent_actions = [
        m.group(1)
        for h in agent_turns[-5:]
        for m in [re.search(r"^\[(\w+)\]", str(h.get("content", "")))]
        if m
    ]
    action_loop = len(recent_actions) >= 3 and len(set(recent_actions[-3:])) == 1

    is_stuck = (
        action_loop
        or recent_contents.count("could not parse") >= 1
        or recent_contents.count("error") >= 2
    )

    # Always use planner on auth / login pages — small executor model loses the thread
    url_lower = (url or "").lower()
    is_auth_page = any(kw in url_lower for kw in [
        "signin", "login", "auth", "myap.collegeboard", "accounts.google", "account.",
    ])

    use_planner = is_stuck or is_auth_page
    model = BROWSER_PLANNER_MODEL if use_planner else BROWSER_EXECUTOR_MODEL
    system_prompt = _PLANNER_SYSTEM if use_planner else _EXECUTOR_SYSTEM
    num_ctx = 3072 if use_planner else 2048
    num_predict = 128 if use_planner else 80
    num_batch = 256

    # Inject confirmed URL for any known service mentioned in the message
    msg_lower = message.lower()
    url_hints: list[str] = [
        f'"{name}" is at {target_url}'
        for name, target_url in _SERVICE_URLS.items()
        if name in msg_lower
    ]
    url_hint_block = ("Known URLs (use exactly):\n" + "\n".join(f"  {h}" for h in url_hints) + "\n\n") if url_hints else ""

    page_block = (
        f"Current URL: {url or '(unknown)'}\n"
        f"Page title:  {title or '(unknown)'}\n\n"
        f"Page content:\n{(page_text or '(empty)').strip()[:2000 if not use_planner else 2500]}"
    )

    retry_note = ""
    if action_loop:
        looped = recent_actions[-1]
        retry_note = (
            f"WARNING: You have repeated [{looped}] multiple times with no progress. "
            "The page has NOT changed. You MUST try a completely different action — "
            "scroll down to find more elements, try different coordinates, or wait.\n\n"
        )

    user_prompt = (
        f"{retry_note}"
        f"{url_hint_block}"
        f"Page state:\n{page_block}\n\n"
        f"User instruction: {message}\n\n"
        "Output JSON only:"
    )

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for turn in history[-(4 if not use_planner else 6):]:
        role = str(turn.get("role", "user"))
        content = str(turn.get("content", "")).strip()
        if content and role in ("user", "agent", "assistant"):
            messages.append({"role": "user" if role == "user" else "assistant", "content": content})
    messages.append({"role": "user", "content": user_prompt})

    raw = await ollama_client.chat_full(
        model=model,
        messages=messages,
        temperature=0.1,
        num_ctx=num_ctx,
        num_predict=num_predict,
        num_batch=num_batch,
        repeat_penalty=1.05,
        think=False,
        num_gpu=BROWSER_NUM_GPU,  # None = Ollama splits layers across GPU+CPU automatically
        json_format=True,         # constrained decoding — guaranteed valid JSON, no parse failures
        keep_alive=BROWSER_KEEP_ALIVE,
    )

    parsed = _parse_action_strict(raw)
    return _normalize_chat_action(parsed, message=message, url=url, page_text=page_text)
