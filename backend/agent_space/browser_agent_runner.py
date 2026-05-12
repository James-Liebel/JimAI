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
# Legacy run_browser_agent model (unused by Atlas chat panel)
AGENT_MODEL = "qwen2.5-coder:1.5b"

# Atlas chat panel — single mid-weight model, no swapping.
# Using one model eliminates the load/unload cycle between executor and planner,
# which was the main source of fan spin-up. 7b was chosen over 3b because the
# 3b model frequently mis-selected element indices on dense pages (Google
# results, login forms) — the extra reasoning headroom is worth the ~600MB.
BROWSER_MODEL = "qwen2.5-coder:7b"
BROWSER_NUM_GPU = 99          # push all layers to GPU — faster and far less CPU heat
BROWSER_KEEP_ALIVE = "10m"    # longer keep-warm: Atlas sessions easily exceed 5m of think time
BROWSER_VISION_ENABLED = False  # vision adds heavy model swaps; enable only if needed

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
        return {"action": "talk", "thought": f"Could not parse model output: {str(raw or '')[:120]}", "response": "I had trouble understanding that page. Could you describe what you see or try again?"}


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
        "click_index",
        "type_index",
        "click_xy",
        "type_xy",
        "type_chars",
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

    # Coerce string indices to int — LLMs occasionally emit "0" instead of 0.
    for idx_action in ("click_index", "type_index"):
        if action == idx_action and "index" in params:
            try:
                params["index"] = int(params["index"])
            except (TypeError, ValueError):
                params["index"] = -1

    # Fill in minimal defaults so frontend executor always has valid params.
    if action == "click_index":
        params.setdefault("index", -1)
    elif action == "type_index":
        params.setdefault("index", -1)
        params.setdefault("text", "")
        params.setdefault("submit", False)
    elif action == "click_xy":
        params.setdefault("x", 0)
        params.setdefault("y", 0)
    elif action == "type_chars":
        params.setdefault("text", "")
    elif action == "type_xy":
        params.setdefault("x", 0)
        params.setdefault("y", 0)
        params.setdefault("text", "")
    elif action in {"type", "type_and_submit"}:
        params.setdefault("text", "")
    elif action == "navigate":
        params.setdefault("url", "")
    elif action == "press_key":
        params.setdefault("key", "Enter")
    elif action == "scroll":
        params.setdefault("dy", 400)
    # Reject malformed click_index / type_index up front so the executor
    # doesn't waste a step on an invalid index.
    if action == "click_index" and (not isinstance(params.get("index"), int) or params.get("index", -1) < 0):
        action = "wait"
    if action == "type_index" and (not isinstance(params.get("index"), int) or params.get("index", -1) < 0 or not params.get("text")):
        action = "wait"

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
    # Sliding window of (signature, url_at_execution) for the autonomous loop.
    # Mirrors the chat-panel dedup but lives in-memory because run_browser_agent
    # owns the entire stepping loop here.
    sig_history: list[tuple[str, str]] = []
    last_executed_url: str = opened.get("url", start_url)

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

            # Autonomous-mode dedup: if the model emitted the same signature as
            # the previous step and the URL has not moved since, skip executing
            # it. The agent gets to plan again next iteration with the failure
            # implicit in the unchanged state.
            new_sig = _action_signature(action_type, action.get("params") if isinstance(action.get("params"), dict) else action)
            prev_sig = sig_history[-1][0] if sig_history else ""
            prev_url = sig_history[-1][1] if sig_history else ""
            blocked_repeat = (
                bool(new_sig)
                and new_sig == prev_sig
                and bool(current_url)
                and current_url == prev_url
                and action_type not in {"done", "wait", "talk"}
            )

            yield {
                "type": "step",
                "step": step,
                "thought": thought,
                "action": action_type,
                "action_detail": action,
                "screenshot": b64_img,
                "url": current_url,
                "loop_blocked": blocked_repeat,
                "signature": new_sig,
            }

            action_history.append(f"{action_type}: {thought}")
            sig_history.append((new_sig, current_url))

            if blocked_repeat:
                logger.info(
                    "run_browser_agent dedup: blocking repeat sig=%r url=%r",
                    new_sig, current_url,
                )
                # Surface the skip on the SSE stream so the UI can render it.
                yield {
                    "type": "loop_detected",
                    "step": step,
                    "signature": new_sig,
                    "reason": "Same signature as the previous step and the URL did not change.",
                }
                # Do not execute. Wait briefly to let any pending JS settle.
                await asyncio.sleep(0.6)
                continue

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


_BROWSER_SYSTEM = """\
Browser automation agent. Output ONE JSON action — no markdown, no extra text.
Format: {"thought":"one sentence","action":"ACTION","params":{...},"response":"plain English"}

You receive the page as an INDEXED list of interactive elements:
  [0] <button> "Sign in"
  [1] <input type=email> "Email"
  [2] <a href=/signup> "Create account"
Address elements ONLY by their numeric index. Do not write CSS selectors or pixel
coordinates — the executor resolves the index to the real DOM node.

Actions:
  navigate    {"url": "https://..."}                — load a URL in the current tab
  click_index {"index": N}                          — click element [N] from the listing
  type_index  {"index": N, "text": "...", "submit": true|false}
                                                    — focus element [N], type text, optionally press Enter
  press_key   {"key": "Enter"|"Tab"|"Escape"|...}  — send a key to the focused element
  scroll      {"dy": 400}                           — scroll down (positive) or up (negative)
  wait        {}                                    — wait ~1.5s for SPA rendering
  done        {}                                    — goal complete or impossible
  talk        {}                                    — answer the user without acting

Strategy:
1. If you are not on the right site, navigate to a known URL first. Prefer direct
   URLs (e.g. https://accounts.google.com/signin) over clicking through nav menus.
2. After a navigate, the next step you receive will show the new page's indexed
   elements. Pick the one that matches your intent by its label.
3. For login forms: type_index into the email field with submit=false, then
   type_index into the password field with submit=true, OR click_index the
   "Sign in" / "Continue" button.
4. For search boxes: type_index with submit=true, or navigate ?q=query.
5. If FEEDBACK says the last action had no visible effect, the index you picked
   was probably wrong or the click was intercepted — pick a different index, or
   navigate directly to the target URL.
6. Never repeat the exact same {action, index} twice in a row. If it didn't work
   the first time, choose a different element or strategy.
7. If the desired element isn't in the listing, scroll. If still not visible,
   the page may render it lazily — wait, then re-check.
8. Use done when the user's goal is satisfied or definitively impossible.
9. Use talk when the user only asked a question and no browser action is needed.
10. After 2 consecutive no-effect FEEDBACK messages on the same target, change
    strategy entirely: switch to a direct URL navigate, pick a different element
    index, or scroll to expose new elements — never retry the same index a third
    time.
11. Prefer one decisive action per step. Do not narrate plans in `response` —
    keep it to what the user will see ("Searching X…", "Opening Y…").
"""


async def _vision_analyze(screenshot_b64: str, url: str, title: str) -> str:
    """Describe visible interactive elements from a screenshot.

    Only called when the planner is active (stuck or auth page) to supplement
    DOM-extracted context with what the model can actually see on screen.
    """
    if not screenshot_b64:
        return ""
    prompt = (
        f"Web page — URL: {url!r}, title: {title!r}.\n"
        "Identify the interactive elements visible on screen. "
        "For each: element type (button/input/link/etc.), rough position "
        "(top-left / top-center / middle-left / center / etc.), and its visible label or text. "
        "Max 15 items, one per line. Be concise."
    )
    try:
        raw = await asyncio.wait_for(
            ollama_client.chat_full(
                model=BROWSER_VISION_MODEL,
                messages=[{"role": "user", "content": prompt, "images": [screenshot_b64]}],
                temperature=0.1,
                num_ctx=2048,
                num_predict=300,
                think=False,
                num_gpu=BROWSER_NUM_GPU,
                keep_alive=BROWSER_KEEP_ALIVE,
            ),
            timeout=35.0,
        )
        return raw.strip()
    except Exception as exc:
        logger.debug("Vision analysis skipped: %s", exc)
        return ""


_HISTORY_TAG_RE = re.compile(r"^\[(\w+)(?::([^\]]*))?\]")
# Lowered from 3 to 2 — the original 3-strikes rule meant the user always saw the
# same action execute three times before the model received any nudge. With 2, the
# very next call gets feedback.
_REPEAT_TAG_THRESHOLD = 2

# Number of recent agent turns considered when looking for a tag-only repeat.
_REPEAT_TAG_WINDOW = 4


def _action_signature(action: str, params: dict | None) -> str:
    """Return a stable string fingerprint for an Atlas action.

    Two actions are 'the same' iff their signatures match. The signature is
    intentionally narrow: only the verb plus the *primary* identifying param.
    Free-form text (e.g. typed query) is excluded so a user re-typing the same
    search string into a freshly-loaded form is not mis-classified as a loop.
    """
    a = (action or "").strip().lower()
    p = params if isinstance(params, dict) else {}
    if a == "navigate":
        url = str(p.get("url") or "").strip()
        # Normalise to host + path so query-string variants don't drift the sig.
        try:
            parsed = urllib.parse.urlparse(url)
            target = (parsed.netloc + parsed.path).rstrip("/").lower()
        except Exception:
            target = url.lower()
        return f"navigate:{target}" if target else "navigate"
    if a in {"click_index", "type_index"}:
        return f"{a}:{p.get('index', '')}"
    if a == "click_xy" or a == "type_xy":
        return f"{a}:{p.get('x', '')},{p.get('y', '')}"
    if a == "click_selector":
        return f"click_selector:{str(p.get('selector') or '').strip()}"
    if a == "click_link":
        return f"click_link:{str(p.get('href') or '').strip()}"
    if a == "type":
        return f"type:{str(p.get('selector') or '').strip()}"
    if a == "type_and_submit":
        return f"type_and_submit:{str(p.get('selector') or '').strip()}"
    if a == "press_key":
        return f"press_key:{str(p.get('key') or '').strip()}"
    if a == "scroll":
        return f"scroll:{p.get('dy', '')}"
    return a or "unknown"


def _last_history_signature(history: list[dict]) -> str:
    """Read the most recent meaningful agent turn's signature.

    Both the new ``[action:sig]`` content format and the legacy ``[action]``
    format are accepted. Entries whose verb is ``wait`` or ``talk`` are skipped
    because they represent non-actions: a single block from the dedup gate (which
    rewrites to ``wait``) must NOT mask the real signature behind it, otherwise
    a stubborn model emitting nav→nav→nav would only ever be blocked on every
    other turn. Returns ``""`` if no parseable, meaningful tag is present.
    """
    for h in reversed(list(history or [])):
        if str(h.get("role", "")) not in ("agent", "assistant"):
            continue
        m = _HISTORY_TAG_RE.search(str(h.get("content", "")))
        if not m:
            continue
        verb = (m.group(1) or "").lower()
        if verb in {"wait", "talk", "done"}:
            continue
        sig = m.group(2) or ""
        return f"{verb}:{sig}" if sig else verb
    return ""


def _is_no_op_repeat(
    *,
    new_sig: str,
    last_sig: str,
    current_url: str,
    last_url: str,
    action_feedback: str,
) -> bool:
    """Decide whether the about-to-execute action should be BLOCKED.

    The action is blocked only when all three conditions hold:
      1. Its signature exactly matches the last agent turn's signature.
      2. The page URL hasn't changed since the previous action.
      3. The frontend either flagged the previous action as no-effect, OR no
         feedback was sent (treated as "indeterminate, but URL unchanged is
         strong enough on its own when signatures match exactly").

    This deliberately blocks ONLY the second instance of an exact repeat, so a
    user clicking the same toggle twice on purpose (different intent each time)
    is unaffected — the page state will normally have changed between calls.
    """
    if not new_sig or not last_sig or new_sig != last_sig:
        return False
    if not current_url or not last_url:
        # Without a usable URL signal we cannot prove no-effect; do not block,
        # let the feedback-injection path handle it.
        return False
    if current_url != last_url:
        return False
    # URL unchanged + same signature: very likely a no-op repeat. The optional
    # action_feedback string strengthens the signal but isn't required.
    return True


async def chat_browser_step(
    message: str,
    url: str,
    title: str,
    page_text: str,
    history: list[dict],
    screenshot: str = "",
    action_feedback: str = "",
    last_url: str = "",
) -> dict:
    """Single-step browser agent for the Atlas chat panel.

    Uses a single small model with minimal context to keep CPU/GPU load low.
    The frontend handles the execution loop; this function only picks the next action.

    ``last_url`` is the URL the page had **before** the action that produced the
    most recent agent turn ran. The backend uses it to detect no-op repeats in
    the pre-execution gate below.
    """
    # Detect repeated action TAGS. The threshold (now 2 within a 4-turn window)
    # only controls the *prompt feedback* path — the harder pre-execution gate
    # below uses signatures and URL-change to actually block duplicate actions.
    # 'wait' and 'talk' verbs are skipped so a single dedup-block does not mask
    # the underlying repeat pattern.
    agent_turns = [h for h in history if str(h.get("role", "")) in ("agent", "assistant")]
    recent_actions: list[str] = []
    for h in agent_turns[-_REPEAT_TAG_WINDOW * 2:]:  # widen window to absorb wait/talk gaps
        m = _HISTORY_TAG_RE.search(str(h.get("content", "")))
        if not m:
            continue
        verb = (m.group(1) or "").lower()
        if verb in {"wait", "talk", "done"}:
            continue
        recent_actions.append(verb)
    recent_actions = recent_actions[-_REPEAT_TAG_WINDOW:]
    action_loop = (
        len(recent_actions) >= _REPEAT_TAG_THRESHOLD
        and len(set(recent_actions[-_REPEAT_TAG_THRESHOLD:])) == 1
    )

    # Inject confirmed URL for any known service mentioned in the message
    msg_lower = message.lower()
    url_hints: list[str] = [
        f'"{name}" → {target_url}'
        for name, target_url in _SERVICE_URLS.items()
        if name in msg_lower
    ]
    url_hint_block = ("URLs: " + " | ".join(url_hints) + "\n") if url_hints else ""

    # Optional vision pass — disabled by default (heavy model swap)
    vision_block = ""
    if BROWSER_VISION_ENABLED and screenshot and action_loop:
        vision_desc = await _vision_analyze(screenshot, url, title)
        if vision_desc:
            vision_block = f"Visual observation:\n{vision_desc}\n"

    # Build feedback block — action_feedback (from frontend page-diff) takes priority,
    # fall back to loop detection if the frontend didn't send feedback yet.
    feedback_note = ""
    if action_feedback:
        feedback_note = f"{action_feedback}\n"
    elif action_loop:
        looped = recent_actions[-1]
        feedback_note = (
            f"FEEDBACK: [{looped}] repeated with no page change. Try a different approach.\n"
        )

    page_block = (
        f"URL: {url or '(unknown)'}\n"
        f"Title: {title or '(unknown)'}\n"
        f"{vision_block}"
        f"Page:\n{(page_text or '(empty)').strip()[:2400]}"
    )

    user_prompt = (
        f"{feedback_note}"
        f"{url_hint_block}"
        f"{page_block}\n\n"
        f"Task: {message}\nJSON:"
    )

    messages: list[dict] = [{"role": "system", "content": _BROWSER_SYSTEM}]
    # Include last 3 agent turns — wider window helps the model see two failed
    # attempts and the original user goal at the same time.
    for turn in history[-6:]:
        role = str(turn.get("role", "user"))
        content = str(turn.get("content", "")).strip()
        if content and role in ("user", "agent", "assistant"):
            messages.append({"role": "user" if role == "user" else "assistant", "content": content})
    messages.append({"role": "user", "content": user_prompt})

    try:
        raw = await asyncio.wait_for(
            ollama_client.chat_full(
                model=BROWSER_MODEL,
                messages=messages,
                temperature=0.1,
                num_ctx=6144,       # 7b w/ richer page context — 6k keeps full prompt+history+page+JSON
                num_predict=256,    # JSON action + thought + response — 150 truncated on long labels
                num_batch=1024,     # higher prefill parallelism on 7b
                repeat_penalty=1.05,
                think=False,
                top_p=0.8,          # qwen non-thinking sampling — sharper action selection
                top_k=20,
                min_p=0.0,
                num_gpu=BROWSER_NUM_GPU,
                json_format=True,
                keep_alive=BROWSER_KEEP_ALIVE,
            ),
            timeout=60.0,
        )
    except asyncio.TimeoutError:
        logger.warning("chat_browser_step timed out after 60s")
        raw = '{"action":"wait","thought":"Model timed out.","response":"Taking a moment to retry."}'

    parsed = _parse_action_strict(raw)
    normalized = _normalize_chat_action(parsed, message=message, url=url, page_text=page_text)

    # Pre-execution dedup gate. If the model just re-emitted the exact same
    # signature as the last agent turn AND the URL hasn't moved, override to
    # 'wait' so the duplicate never executes. The next turn's prompt will tell
    # the model the previous attempt was a no-op.
    new_sig = _action_signature(normalized.get("action", ""), normalized.get("params"))
    last_sig = _last_history_signature(history)
    if _is_no_op_repeat(
        new_sig=new_sig,
        last_sig=last_sig,
        current_url=url,
        last_url=last_url,
        action_feedback=action_feedback,
    ):
        logger.info(
            "atlas dedup: blocking repeat sig=%r url=%r last_url=%r",
            new_sig, url, last_url,
        )
        return {
            "thought": (
                f"Last action [{last_sig}] did not change the page; "
                "skipping the repeat and choosing a different approach next turn."
            ),
            "action": "wait",
            "params": {},
            "response": (
                "I just tried that and the page didn't change — picking a different "
                "approach next."
            ),
            "loop_blocked": True,
            "blocked_signature": last_sig,
        }

    return normalized
