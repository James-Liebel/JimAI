"""Unit tests for the pure helper functions in ``api/chat.py``.

These cover the deterministic, side-effect-free logic the chat endpoint relies
on: URL/domain parsing, source scoring, citation validation, live-query
heuristics, and browser-capture intent detection. They use the real functions
with no mocking — every helper here is pure input → output.

Run:
    cd backend
    pytest tests/test_chat_helpers.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from api.chat import (
    _build_web_queries,
    _coerce_score,
    _domain_from_url,
    _extract_page_capture_url,
    _is_technical_message,
    _normalize_live_query_text,
    _score_source_relevance,
    _should_attempt_chat_browser_capture,
    _source_url,
    _validate_citations,
)


# ---------------------------------------------------------------------------
# _domain_from_url
# ---------------------------------------------------------------------------

class TestDomainFromUrl:
    def test_strips_www_prefix(self):
        assert _domain_from_url("https://www.example.com/path") == "example.com"

    def test_keeps_subdomain(self):
        assert _domain_from_url("https://docs.python.org/3/") == "docs.python.org"

    def test_empty_returns_unknown(self):
        assert _domain_from_url("") == "unknown"

    def test_schemeless_text_returns_unknown(self):
        assert _domain_from_url("just some words") == "unknown"


# ---------------------------------------------------------------------------
# _coerce_score
# ---------------------------------------------------------------------------

class TestCoerceScore:
    def test_none_returns_none(self):
        assert _coerce_score(None) is None

    def test_in_range_value_preserved(self):
        assert _coerce_score(0.5) == 0.5

    def test_above_one_clamped(self):
        assert _coerce_score(2.0) == 1.0

    def test_below_zero_clamped(self):
        assert _coerce_score(-1.0) == 0.0

    def test_non_numeric_returns_none(self):
        assert _coerce_score("abc") is None

    def test_nan_returns_none(self):
        assert _coerce_score(float("nan")) is None


# ---------------------------------------------------------------------------
# _score_source_relevance
# ---------------------------------------------------------------------------

class TestScoreSourceRelevance:
    def test_all_query_words_present_scores_one(self):
        score = _score_source_relevance("python flask", "Python Flask Guide", "", "")
        assert score == 1.0

    def test_partial_match_scores_fraction(self):
        score = _score_source_relevance("python flask", "Python tutorial", "", "")
        assert score == 0.5

    def test_no_long_words_scores_zero(self):
        # All tokens are <= 3 chars, so there are no scorable query words.
        assert _score_source_relevance("is on a to", "anything here", "", "") == 0.0


# ---------------------------------------------------------------------------
# _source_url
# ---------------------------------------------------------------------------

class TestSourceUrl:
    def test_http_url_passes_through(self):
        assert _source_url("https://example.com") == "https://example.com"

    def test_non_http_returns_empty(self):
        assert _source_url("ftp://example.com") == ""

    def test_surrounding_whitespace_trimmed(self):
        assert _source_url("  http://example.com  ") == "http://example.com"


# ---------------------------------------------------------------------------
# _is_technical_message
# ---------------------------------------------------------------------------

class TestIsTechnicalMessage:
    def test_code_fence_is_technical(self):
        assert _is_technical_message("here is code:\n```\nx = 1\n```") is True

    def test_plain_greeting_is_not_technical(self):
        assert _is_technical_message("hello there friend") is False

    def test_empty_is_not_technical(self):
        assert _is_technical_message("") is False


# ---------------------------------------------------------------------------
# _normalize_live_query_text
# ---------------------------------------------------------------------------

class TestNormalizeLiveQueryText:
    def test_lowercases_and_collapses_whitespace(self):
        assert _normalize_live_query_text("  Hello   World  ") == "hello world"

    def test_empty_returns_empty(self):
        assert _normalize_live_query_text("") == ""

    def test_power_strap_collapsed_to_single_token(self):
        assert _normalize_live_query_text("power strap") == "powerstrap"


# ---------------------------------------------------------------------------
# _build_web_queries
# ---------------------------------------------------------------------------

class TestBuildWebQueries:
    def test_empty_returns_no_queries(self):
        assert _build_web_queries("") == []

    def test_original_message_is_first_query(self):
        queries = _build_web_queries("best running shoes")
        assert queries[0] == "best running shoes"

    def test_queries_are_deduped_and_capped_at_ten(self):
        queries = _build_web_queries("cheapest price of nike pegasus in stock at amazon")
        assert len(queries) == len(set(q.lower() for q in queries)) <= 10


# ---------------------------------------------------------------------------
# _validate_citations
# ---------------------------------------------------------------------------

class TestValidateCitations:
    def test_empty_response_has_no_issues(self):
        assert _validate_citations("any question", "", []) == []

    def test_citation_not_in_sources_is_flagged(self):
        issues = _validate_citations(
            "general question",
            "See [1] https://made-up-source.com/x for details.",
            [{"source": "https://real-source.com"}],
        )
        assert any("not in research sources" in issue for issue in issues)

    def test_citation_in_sources_on_neutral_topic_is_clean(self):
        issues = _validate_citations(
            "general question",
            "See [1] https://real-source.com/page for details.",
            [{"source": "https://real-source.com/page"}],
        )
        assert issues == []

    def test_off_topic_domain_for_finance_question_is_flagged(self):
        issues = _validate_citations(
            "finance valuation dcf model",
            "Per [1] https://stackoverflow.com/questions/123 the value is X.",
            [{"source": "https://stackoverflow.com/questions/123"}],
        )
        assert any("off-topic" in issue for issue in issues)


# ---------------------------------------------------------------------------
# _extract_page_capture_url
# ---------------------------------------------------------------------------

class TestExtractPageCaptureUrl:
    def test_empty_returns_none(self):
        assert _extract_page_capture_url("") is None

    def test_explicit_https_url_extracted_and_trailing_punctuation_stripped(self):
        assert _extract_page_capture_url("take a screenshot of https://example.com.") == "https://example.com"

    def test_localhost_gets_http_scheme(self):
        assert _extract_page_capture_url("open localhost:3000") == "http://localhost:3000"

    def test_github_shorthand_becomes_profile_url(self):
        assert _extract_page_capture_url("show me github.com/torvalds") == "https://github.com/torvalds"

    def test_prose_without_url_returns_none(self):
        assert _extract_page_capture_url("tell me a fun fact") is None


# ---------------------------------------------------------------------------
# _should_attempt_chat_browser_capture
# ---------------------------------------------------------------------------

class TestShouldAttemptChatBrowserCapture:
    def test_empty_message_is_false(self):
        assert _should_attempt_chat_browser_capture("", "chat") is False

    def test_screenshot_verb_with_url_is_true(self):
        assert _should_attempt_chat_browser_capture(
            "take a screenshot of https://example.com", "chat"
        ) is True

    def test_plain_chat_without_url_is_false(self):
        assert _should_attempt_chat_browser_capture("tell me a fun fact", "chat") is False
