"""Goal-directed tests for the Atlas browser automation agent.

Each test feeds a clear goal (or page state) to the agent functions and verifies
that the agent correctly parses model output, normalises actions, builds prompts,
and — when the LLM is mocked — returns the right next action for the goal.

Run:
    cd backend
    pytest tests/test_atlas_agent.py -v
"""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.parse
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import agent_space.browser_agent_runner as runner
from agent_space.browser_agent_runner import (
    _build_page_context,
    _normalize_chat_action,
    _parse_action,
    _parse_action_strict,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _action_json(**kwargs) -> str:
    return json.dumps({"thought": "test", "response": "ok", **kwargs})


# ---------------------------------------------------------------------------
# _parse_action
# ---------------------------------------------------------------------------

class TestParseAction:
    def test_clean_json_returns_dict(self):
        raw = '{"action": "navigate", "params": {"url": "https://example.com"}, "thought": "going there"}'
        result = _parse_action(raw)
        assert result["action"] == "navigate"
        assert result["params"]["url"] == "https://example.com"

    def test_json_in_markdown_fence_extracted(self):
        raw = '```json\n{"action": "done", "result": "finished"}\n```'
        result = _parse_action(raw)
        assert result["action"] == "done"

    def test_json_in_plain_fence_extracted(self):
        raw = '```\n{"action": "wait"}\n```'
        result = _parse_action(raw)
        assert result["action"] == "wait"

    def test_think_tags_stripped_before_parse(self):
        raw = '<think>I need to click the button</think>\n{"action": "click_index", "params": {"index": 0}}'
        result = _parse_action(raw)
        assert result["action"] == "click_index"

    def test_json_embedded_in_prose_extracted(self):
        raw = 'I will navigate now. {"action": "navigate", "params": {"url": "https://google.com"}} Done.'
        result = _parse_action(raw)
        assert result["action"] == "navigate"

    def test_garbage_returns_talk_fallback(self):
        result = _parse_action("this is definitely not JSON at all!!")
        assert result["action"] == "talk"
        assert "response" in result

    def test_empty_string_returns_talk_fallback(self):
        result = _parse_action("")
        assert result["action"] == "talk"

    def test_none_input_returns_talk_fallback(self):
        result = _parse_action(None)  # type: ignore[arg-type]
        assert result["action"] == "talk"


# ---------------------------------------------------------------------------
# _parse_action_strict
# ---------------------------------------------------------------------------

class TestParseActionStrict:
    def test_clean_json_returns_dict(self):
        raw = '{"action": "click_index", "params": {"index": 3}}'
        result = _parse_action_strict(raw)
        assert isinstance(result, dict)
        assert result["action"] == "click_index"

    def test_trailing_comma_fixed(self):
        raw = '{"action": "navigate", "params": {"url": "https://x.com"},}'
        result = _parse_action_strict(raw)
        assert result is not None
        assert result["action"] == "navigate"

    def test_trailing_comma_in_nested_object_fixed(self):
        raw = '{"action": "type_index", "params": {"index": 1, "text": "hello",}}'
        result = _parse_action_strict(raw)
        assert result is not None
        assert result["params"]["text"] == "hello"

    def test_curly_quotes_replaced(self):
        raw = '“{"action": "wait"}”'
        result = _parse_action_strict(raw)
        assert result is not None
        assert result["action"] == "wait"

    def test_empty_string_returns_none(self):
        assert _parse_action_strict("") is None

    def test_whitespace_only_returns_none(self):
        assert _parse_action_strict("   ") is None

    def test_pure_garbage_returns_none(self):
        assert _parse_action_strict("not json at all blah blah") is None

    def test_think_tags_stripped(self):
        raw = "<think>reasoning</think>\n{\"action\": \"done\"}"
        result = _parse_action_strict(raw)
        assert result is not None
        assert result["action"] == "done"

    def test_json_in_fence_extracted(self):
        raw = "```json\n{\"action\": \"scroll\", \"params\": {\"dy\": 400}}\n```"
        result = _parse_action_strict(raw)
        assert result is not None
        assert result["action"] == "scroll"


# ---------------------------------------------------------------------------
# _normalize_chat_action
# ---------------------------------------------------------------------------

class TestNormalizeChatAction:
    def _norm(self, parsed, *, message="do something", url="https://example.com", page_text="page"):
        return _normalize_chat_action(parsed, message=message, url=url, page_text=page_text)

    # --- action pass-through ---
    def test_valid_navigate_passes_through(self):
        parsed = {"action": "navigate", "params": {"url": "https://google.com"}, "thought": "go", "response": "going"}
        result = self._norm(parsed)
        assert result["action"] == "navigate"
        assert result["params"]["url"] == "https://google.com"

    def test_valid_click_index_passes_through(self):
        parsed = {"action": "click_index", "params": {"index": 2}, "thought": "click", "response": "clicking"}
        result = self._norm(parsed)
        assert result["action"] == "click_index"
        assert result["params"]["index"] == 2

    def test_valid_done_passes_through(self):
        parsed = {"action": "done", "params": {}, "thought": "finished", "response": "done"}
        result = self._norm(parsed)
        assert result["action"] == "done"

    # --- index validation ---
    def test_click_index_negative_becomes_wait(self):
        parsed = {"action": "click_index", "params": {"index": -1}, "thought": "t", "response": "r"}
        result = self._norm(parsed)
        assert result["action"] == "wait"

    def test_click_index_string_index_coerced_to_int(self):
        parsed = {"action": "click_index", "params": {"index": "5"}, "thought": "t", "response": "r"}
        result = self._norm(parsed)
        assert result["action"] == "click_index"
        assert result["params"]["index"] == 5

    def test_click_index_zero_string_coerced_passes(self):
        parsed = {"action": "click_index", "params": {"index": "0"}, "thought": "t", "response": "r"}
        result = self._norm(parsed)
        assert result["action"] == "click_index"
        assert result["params"]["index"] == 0

    def test_click_index_non_numeric_string_becomes_wait(self):
        parsed = {"action": "click_index", "params": {"index": "abc"}, "thought": "t", "response": "r"}
        result = self._norm(parsed)
        assert result["action"] == "wait"

    def test_type_index_empty_text_becomes_wait(self):
        parsed = {"action": "type_index", "params": {"index": 1, "text": ""}, "thought": "t", "response": "r"}
        result = self._norm(parsed)
        assert result["action"] == "wait"

    def test_type_index_negative_index_becomes_wait(self):
        parsed = {"action": "type_index", "params": {"index": -3, "text": "hello"}, "thought": "t", "response": "r"}
        result = self._norm(parsed)
        assert result["action"] == "wait"

    def test_type_index_string_index_coerced(self):
        parsed = {"action": "type_index", "params": {"index": "2", "text": "hello"}, "thought": "t", "response": "r"}
        result = self._norm(parsed)
        assert result["action"] == "type_index"
        assert result["params"]["index"] == 2

    # --- unknown action ---
    def test_unknown_action_becomes_wait(self):
        parsed = {"action": "teleport", "params": {}, "thought": "t", "response": "r"}
        result = self._norm(parsed)
        assert result["action"] == "wait"

    # --- parse failure ---
    def test_parsed_none_becomes_wait(self):
        result = self._norm(None)
        assert result["action"] == "wait"
        assert result["response"]

    # --- Google search rewrite ---
    def test_type_on_google_search_box_rewrites_to_navigate(self):
        parsed = {
            "action": "type",
            "params": {"selector": "textarea", "text": "python tutorials"},
            "thought": "searching",
            "response": "searching",
        }
        result = self._norm(parsed, url="https://www.google.com")
        assert result["action"] == "navigate"
        assert "python+tutorials" in result["params"]["url"].lower()

    def test_type_and_submit_on_google_results_becomes_click_selector(self):
        # Use a selector that does NOT match the "textarea"/"input" rewrite so the
        # second check (already on Google results → click top result) fires instead.
        parsed = {
            "action": "type_and_submit",
            "params": {"selector": "#search", "text": "query"},
            "thought": "t",
            "response": "r",
        }
        result = self._norm(parsed, url="https://www.google.com/search?q=old")
        assert result["action"] == "click_selector"
        assert result["params"]["selector"] == "a h3"

    # --- defaults injected ---
    def test_navigate_url_default_empty_string(self):
        parsed = {"action": "navigate", "params": {}, "thought": "t", "response": "r"}
        result = self._norm(parsed)
        assert result["params"]["url"] == ""

    def test_press_key_default_enter(self):
        parsed = {"action": "press_key", "params": {}, "thought": "t", "response": "r"}
        result = self._norm(parsed)
        assert result["params"]["key"] == "Enter"

    def test_scroll_default_dy(self):
        parsed = {"action": "scroll", "params": {}, "thought": "t", "response": "r"}
        result = self._norm(parsed)
        assert result["params"]["dy"] == 400

    # --- response handling ---
    def test_response_truncated_to_260_chars(self):
        parsed = {"action": "wait", "params": {}, "thought": "t", "response": "x" * 500}
        result = self._norm(parsed)
        assert len(result["response"]) == 260

    def test_response_falls_back_to_thought(self):
        parsed = {"action": "wait", "params": {}, "thought": "thinking hard", "response": ""}
        result = self._norm(parsed)
        assert result["response"] == "thinking hard"

    def test_empty_response_and_thought_fills_default(self):
        parsed = {"action": "wait", "params": {}, "thought": "", "response": ""}
        result = self._norm(parsed)
        assert result["response"]


# ---------------------------------------------------------------------------
# _build_page_context
# ---------------------------------------------------------------------------

class TestBuildPageContext:
    def test_url_and_title_always_present(self):
        ctx = _build_page_context("https://example.com", "Example", "", [], [])
        assert "URL: https://example.com" in ctx
        assert "Title: Example" in ctx

    def test_interactive_elements_listed(self):
        elems = [
            {"selector": "button.login", "tag": "button", "label": "Sign in", "type": "submit"},
            {"selector": "input#email", "tag": "input", "type": "email", "label": "Email"},
        ]
        ctx = _build_page_context("https://example.com", "t", "", elems, [])
        assert "Interactive elements:" in ctx
        assert "Sign in" in ctx
        assert "Email" in ctx

    def test_interactive_limited_to_30(self):
        elems = [{"selector": f"btn-{i}", "tag": "button", "label": f"btn{i}", "type": "button"} for i in range(50)]
        ctx = _build_page_context("https://x.com", "t", "", elems, [])
        # Count rendered element lines — each line contains "[button/button]" exactly once.
        assert ctx.count("[button/button]") <= 30

    def test_links_listed(self):
        links = [{"href": "/about", "text": "About us"}, {"href": "/contact", "text": "Contact"}]
        ctx = _build_page_context("https://example.com", "t", "", [], links)
        assert "Links" in ctx
        assert "About us" in ctx

    def test_links_limited_to_20(self):
        links = [{"href": f"/page{i}", "text": f"Page {i}"} for i in range(30)]
        ctx = _build_page_context("https://x.com", "t", "", [], links)
        assert ctx.count("Page ") <= 20

    def test_page_text_included(self):
        ctx = _build_page_context("https://x.com", "t", "Welcome to our site", [], [])
        assert "Welcome to our site" in ctx

    def test_page_text_trimmed_to_3000(self):
        long_text = "a" * 5000
        ctx = _build_page_context("https://x.com", "t", long_text, [], [])
        text_portion = ctx.split("Page text:")[-1] if "Page text:" in ctx else ctx
        assert len(text_portion) <= 3100  # trim + surrounding newlines

    def test_empty_inputs_no_crash(self):
        ctx = _build_page_context("", "", "", [], [])
        assert isinstance(ctx, str)


# ---------------------------------------------------------------------------
# Goal-directed integration tests (mocked LLM)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
class TestGoalDirectedScenarios:
    """Feed a clear goal + page state, verify the agent picks the correct next action."""

    def _make_mock_ollama(self, response_json: str):
        mock = MagicMock()
        mock.chat_full = AsyncMock(return_value=response_json)
        return mock

    async def test_goal_navigate_to_known_service(self):
        """Goal: 'Go to AP Classroom'. Agent should navigate to the known URL."""
        model_resp = _action_json(
            action="navigate",
            params={"url": "https://myap.collegeboard.org"},
            response="Navigating to AP Classroom.",
        )
        with patch.object(runner, "ollama_client", self._make_mock_ollama(model_resp)):
            result = await runner.chat_browser_step(
                message="Go to AP Classroom",
                url="about:blank",
                title="New Tab",
                page_text="",
                history=[],
            )
        assert result["action"] == "navigate"
        assert "collegeboard" in result["params"]["url"]

    async def test_url_hint_injected_for_known_service(self):
        """AP Classroom mention in message → URL hint appears in prompt → model uses correct URL."""
        captured_messages: list = []

        async def capturing_chat_full(model, messages, **kwargs):
            captured_messages.extend(messages)
            return _action_json(
                action="navigate",
                params={"url": "https://myap.collegeboard.org"},
                response="Going there.",
            )

        mock_oc = MagicMock()
        mock_oc.chat_full = capturing_chat_full
        with patch.object(runner, "ollama_client", mock_oc):
            await runner.chat_browser_step(
                message="sign in to ap classroom",
                url="about:blank",
                title="",
                page_text="",
                history=[],
            )

        full_prompt = " ".join(m.get("content", "") for m in captured_messages)
        assert "myap.collegeboard.org" in full_prompt

    async def test_goal_search_on_google_homepage(self):
        """Goal: search for 'python tutorials'. Agent on Google should navigate to search URL."""
        model_resp = _action_json(
            action="type_index",
            params={"index": 0, "text": "python tutorials", "submit": True},
            response="Typing search query.",
        )
        with patch.object(runner, "ollama_client", self._make_mock_ollama(model_resp)):
            result = await runner.chat_browser_step(
                message="search for python tutorials",
                url="https://www.google.com",
                title="Google",
                page_text="Search the web",
                history=[],
            )
        assert result["action"] == "type_index"
        assert result["params"]["index"] == 0
        assert result["params"]["text"] == "python tutorials"

    async def test_goal_click_to_open_result(self):
        """Goal: open the first result. Agent on a search results page should click."""
        model_resp = _action_json(
            action="click_index",
            params={"index": 0},
            response="Opening the first result.",
        )
        with patch.object(runner, "ollama_client", self._make_mock_ollama(model_resp)):
            result = await runner.chat_browser_step(
                message="open the first Python tutorial",
                url="https://www.google.com/search?q=python+tutorials",
                title="python tutorials - Google Search",
                page_text="[0] Python.org Official Tutorial ...",
                history=[],
            )
        assert result["action"] == "click_index"
        assert result["params"]["index"] == 0

    async def test_loop_detection_injects_feedback_in_prompt(self):
        """When history shows the same action 3x, FEEDBACK must appear in the prompt."""
        captured: list = []

        async def capturing_chat_full(model, messages, **kwargs):
            captured.extend(messages)
            return _action_json(action="navigate", params={"url": "https://x.com"}, response="trying different")

        history = [
            {"role": "agent", "content": "[navigate] Going to example.com"},
            {"role": "agent", "content": "[navigate] Going to example.com"},
            {"role": "agent", "content": "[navigate] Going to example.com"},
        ]
        mock_oc = MagicMock()
        mock_oc.chat_full = capturing_chat_full
        with patch.object(runner, "ollama_client", mock_oc):
            await runner.chat_browser_step(
                message="go to example.com",
                url="https://example.com",
                title="Example",
                page_text="Example domain.",
                history=history,
            )
        full_prompt = " ".join(m.get("content", "") for m in captured)
        assert "FEEDBACK" in full_prompt

    async def test_action_feedback_from_frontend_overrides_loop_detection(self):
        """Explicit action_feedback from frontend takes priority over loop-detection."""
        captured: list = []

        async def capturing_chat_full(model, messages, **kwargs):
            captured.extend(messages)
            return _action_json(action="scroll", params={"dy": 400}, response="scrolling")

        history = [
            {"role": "agent", "content": "[navigate] page 1"},
            {"role": "agent", "content": "[navigate] page 1"},
            {"role": "agent", "content": "[navigate] page 1"},
        ]
        mock_oc = MagicMock()
        mock_oc.chat_full = capturing_chat_full
        with patch.object(runner, "ollama_client", mock_oc):
            await runner.chat_browser_step(
                message="find the sign-in button",
                url="https://x.com",
                title="x",
                page_text="page",
                history=history,
                action_feedback="FEEDBACK: URL changed to /login",
            )
        full_prompt = " ".join(m.get("content", "") for m in captured)
        assert "FEEDBACK: URL changed to /login" in full_prompt

    async def test_goal_done_when_task_complete(self):
        """When goal is satisfied, agent should return action=done."""
        model_resp = _action_json(
            action="done",
            params={},
            response="The AP course list is now visible.",
        )
        with patch.object(runner, "ollama_client", self._make_mock_ollama(model_resp)):
            result = await runner.chat_browser_step(
                message="Show my AP courses list",
                url="https://myap.collegeboard.org/courses",
                title="My AP Courses",
                page_text="AP Calculus BC  AP Physics 1  AP English Literature",
                history=[],
            )
        assert result["action"] == "done"
        assert result["response"]

    async def test_timeout_returns_wait_action(self):
        """When ollama_client times out, agent returns wait gracefully."""
        import asyncio as _asyncio

        async def timeout_chat_full(*args, **kwargs):
            raise _asyncio.TimeoutError()

        mock_oc = MagicMock()
        mock_oc.chat_full = timeout_chat_full
        with patch.object(runner, "ollama_client", mock_oc):
            result = await runner.chat_browser_step(
                message="go to google",
                url="about:blank",
                title="",
                page_text="",
                history=[],
            )
        assert result["action"] == "wait"
        assert result["response"]

    async def test_malformed_model_output_recovers_gracefully(self):
        """When model returns garbage, agent returns wait with a helpful response."""
        with patch.object(runner, "ollama_client", self._make_mock_ollama("THIS IS NOT JSON")):
            result = await runner.chat_browser_step(
                message="navigate to github.com",
                url="about:blank",
                title="",
                page_text="",
                history=[],
            )
        assert result["action"] == "wait"
        assert isinstance(result["response"], str)
        assert len(result["response"]) > 0

    async def test_multi_step_goal_sequence(self):
        """Simulate a 3-step goal: blank → Google → search → done."""
        responses = iter([
            _action_json(action="navigate", params={"url": "https://www.google.com"}, response="Going to Google."),
            _action_json(action="type_index", params={"index": 0, "text": "Khan Academy calculus", "submit": True}, response="Searching."),
            _action_json(action="done", params={}, response="Found Khan Academy calculus results."),
        ])

        async def sequential_chat_full(*args, **kwargs):
            return next(responses)

        mock_oc = MagicMock()
        mock_oc.chat_full = sequential_chat_full

        goal = "Find Khan Academy calculus on Google"
        history = []

        with patch.object(runner, "ollama_client", mock_oc):
            step1 = await runner.chat_browser_step(
                message=goal, url="about:blank", title="New Tab", page_text="", history=history
            )
            history.append({"role": "agent", "content": f"[{step1['action']}] {step1['response']}"})

            step2 = await runner.chat_browser_step(
                message=goal, url="https://www.google.com", title="Google",
                page_text="Search the web", history=history
            )
            history.append({"role": "agent", "content": f"[{step2['action']}] {step2['response']}"})

            step3 = await runner.chat_browser_step(
                message=goal, url="https://www.google.com/search?q=Khan+Academy+calculus",
                title="Khan Academy calculus - Google Search",
                page_text="Khan Academy | Free online courses, lessons & practice",
                history=history,
            )

        assert step1["action"] == "navigate"
        assert step2["action"] == "type_index"
        assert step3["action"] == "done"

    async def test_goal_with_no_history_uses_full_page_context(self):
        """On first step, no history — full page context should be in the prompt."""
        captured: list = []

        async def capturing_chat_full(model, messages, **kwargs):
            captured.extend(messages)
            return _action_json(action="click_index", params={"index": 1}, response="clicking")

        mock_oc = MagicMock()
        mock_oc.chat_full = capturing_chat_full
        with patch.object(runner, "ollama_client", mock_oc):
            await runner.chat_browser_step(
                message="sign in",
                url="https://accounts.google.com",
                title="Sign in - Google Accounts",
                page_text="Email or phone  Forgot email?  Create account",
                history=[],
            )

        full_prompt = " ".join(m.get("content", "") for m in captured)
        assert "accounts.google.com" in full_prompt
        assert "Sign in - Google Accounts" in full_prompt
        assert "Email or phone" in full_prompt


# ---------------------------------------------------------------------------
# Action signature + dedup gate (Atlas anti-loop)
# ---------------------------------------------------------------------------


class TestActionSignature:
    """_action_signature is the fingerprint behind every dedup decision."""

    def test_navigate_signature_strips_query_string(self):
        sig_a = runner._action_signature("navigate", {"url": "https://www.google.com/search?q=foo"})
        sig_b = runner._action_signature("navigate", {"url": "https://www.google.com/search?q=bar"})
        # Same host + path -> same signature regardless of query string
        assert sig_a == sig_b == "navigate:www.google.com/search"

    def test_navigate_different_hosts_different_signatures(self):
        sig_a = runner._action_signature("navigate", {"url": "https://google.com"})
        sig_b = runner._action_signature("navigate", {"url": "https://bing.com"})
        assert sig_a != sig_b

    def test_click_index_signature_includes_index(self):
        sig0 = runner._action_signature("click_index", {"index": 0})
        sig1 = runner._action_signature("click_index", {"index": 1})
        assert sig0 == "click_index:0"
        assert sig1 == "click_index:1"
        assert sig0 != sig1

    def test_type_signature_excludes_freeform_text(self):
        sig_a = runner._action_signature("type", {"selector": "#q", "text": "alpha"})
        sig_b = runner._action_signature("type", {"selector": "#q", "text": "beta"})
        # Free-form text intentionally not part of sig — re-typing same field
        # for a different query is not a loop.
        assert sig_a == sig_b == "type:#q"

    def test_unknown_action_returns_verb(self):
        assert runner._action_signature("teleport", {}) == "teleport"
        assert runner._action_signature("", {}) == "unknown"


class TestLastHistorySignature:
    def test_picks_most_recent_meaningful_entry(self):
        history = [
            {"role": "user", "content": "go"},
            {"role": "agent", "content": "[navigate:google.com] going there"},
            {"role": "agent", "content": "[click_index:2] clicking"},
        ]
        assert runner._last_history_signature(history) == "click_index:2"

    def test_skips_wait_and_talk_entries(self):
        history = [
            {"role": "agent", "content": "[navigate:google.com] going"},
            {"role": "agent", "content": "[wait] paused"},
            {"role": "agent", "content": "[talk] hi"},
        ]
        # wait + talk are skipped, navigate is the most recent meaningful entry.
        assert runner._last_history_signature(history) == "navigate:google.com"

    def test_legacy_format_still_matches(self):
        history = [{"role": "agent", "content": "[click_index] clicking"}]
        # Legacy entries without ":sig" fall back to verb only.
        assert runner._last_history_signature(history) == "click_index"

    def test_no_match_returns_empty(self):
        assert runner._last_history_signature([]) == ""
        assert runner._last_history_signature([{"role": "user", "content": "no tag"}]) == ""


@pytest.mark.anyio
class TestDedupGate:
    """Pre-execution gate: identical signature + URL unchanged -> wait."""

    def _mock(self, response_json: str):
        mock = MagicMock()
        mock.chat_full = AsyncMock(return_value=response_json)
        return mock

    async def test_repeat_navigate_with_unchanged_url_is_blocked(self):
        history = [{"role": "agent", "content": "[navigate:www.google.com] going"}]
        # Model emits the same navigate even though we're already there.
        model_resp = _action_json(
            action="navigate",
            params={"url": "https://www.google.com"},
            response="going to google",
        )
        with patch.object(runner, "ollama_client", self._mock(model_resp)):
            result = await runner.chat_browser_step(
                message="open google",
                url="https://www.google.com",
                last_url="https://www.google.com",
                title="Google",
                page_text="Google",
                history=history,
            )
        assert result["action"] == "wait"
        assert result.get("loop_blocked") is True
        assert result.get("blocked_signature") == "navigate:www.google.com"

    async def test_different_navigate_target_not_blocked(self):
        history = [{"role": "agent", "content": "[navigate:www.google.com] step 1"}]
        # Model picks a different host this time -> sig differs -> allowed.
        model_resp = _action_json(
            action="navigate",
            params={"url": "https://duckduckgo.com"},
            response="trying ddg",
        )
        with patch.object(runner, "ollama_client", self._mock(model_resp)):
            result = await runner.chat_browser_step(
                message="search",
                url="https://www.google.com",
                last_url="https://www.google.com",
                title="Google",
                page_text="Google",
                history=history,
            )
        assert result["action"] == "navigate"
        assert result.get("loop_blocked") is not True

    async def test_repeat_click_index_url_changed_is_allowed(self):
        history = [{"role": "agent", "content": "[click_index:0] step 1"}]
        # Same click_index:0, but the URL has moved since last action,
        # which means the previous click had effect — allow another one.
        model_resp = _action_json(
            action="click_index",
            params={"index": 0},
            response="clicking again",
        )
        with patch.object(runner, "ollama_client", self._mock(model_resp)):
            result = await runner.chat_browser_step(
                message="click first result",
                url="https://example.com/page2",
                last_url="https://example.com/page1",
                title="x",
                page_text="x",
                history=history,
            )
        assert result["action"] == "click_index"
        assert result.get("loop_blocked") is not True

    async def test_no_last_url_falls_back_to_feedback_path(self):
        # Without last_url we cannot prove no-effect, so the gate stays open and
        # the existing FEEDBACK injection path covers things.
        captured: list = []

        async def capturing(model, messages, **kwargs):
            captured.extend(messages)
            return _action_json(
                action="navigate",
                params={"url": "https://www.google.com"},
                response="going",
            )
        mock_oc = MagicMock()
        mock_oc.chat_full = capturing
        history = [
            {"role": "agent", "content": "[navigate:www.google.com] step 1"},
            {"role": "agent", "content": "[navigate:www.google.com] step 2"},
        ]
        with patch.object(runner, "ollama_client", mock_oc):
            result = await runner.chat_browser_step(
                message="open google",
                url="https://www.google.com",
                last_url="",  # no signal -> gate stays open
                title="Google",
                page_text="Google",
                history=history,
            )
        # Action is allowed through (no last_url means no proof of no-op)
        assert result["action"] == "navigate"
        # But FEEDBACK was injected (threshold is 2; we have 2 prior navigates).
        full = " ".join(m.get("content", "") for m in captured)
        assert "FEEDBACK" in full

    async def test_block_persists_across_intervening_wait(self):
        # If a previous block rewrote the action to wait, the subsequent emit
        # must still match against the underlying real action — not the wait.
        history = [
            {"role": "agent", "content": "[navigate:www.google.com] step 1"},
            {"role": "agent", "content": "[wait] just tried that"},
        ]
        model_resp = _action_json(
            action="navigate",
            params={"url": "https://www.google.com"},
            response="trying again",
        )
        with patch.object(runner, "ollama_client", self._mock(model_resp)):
            result = await runner.chat_browser_step(
                message="open google",
                url="https://www.google.com",
                last_url="https://www.google.com",
                title="Google",
                page_text="Google",
                history=history,
            )
        # The wait between the two navigates is skipped; sig still matches.
        assert result["action"] == "wait"
        assert result.get("loop_blocked") is True

    async def test_lowered_feedback_threshold_fires_after_two(self):
        captured: list = []

        async def capturing(model, messages, **kwargs):
            captured.extend(messages)
            return _action_json(
                action="navigate",
                params={"url": "https://www.bing.com"},
                response="trying bing",
            )
        mock_oc = MagicMock()
        mock_oc.chat_full = capturing
        # Only TWO prior matching tags — under the old threshold of 3 this
        # would have been silent. Under the new threshold of 2 it fires.
        history = [
            {"role": "agent", "content": "[navigate:google.com] step 1"},
            {"role": "agent", "content": "[navigate:google.com] step 2"},
        ]
        with patch.object(runner, "ollama_client", mock_oc):
            await runner.chat_browser_step(
                message="open google",
                url="https://www.bing.com",         # URL different so dedup gate stays open
                last_url="https://www.google.com",
                title="Bing",
                page_text="Bing",
                history=history,
            )
        full = " ".join(m.get("content", "") for m in captured)
        assert "FEEDBACK" in full
