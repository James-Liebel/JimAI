"""Tests for browser_agent.py navigation retry.

Playwright navigation hits transient connection errors (resets, timeouts) that
are distinct from the Ollama HTTP layer. `_goto_with_retry` retries those a
configurable number of times while failing fast on permanent errors.

Run:
    cd backend
    pytest tests/test_browser_agent.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agent_space.browser_agent import _goto_with_retry, _is_transient_nav_error


class TestIsTransientNavError:
    def test_connection_reset_is_transient(self):
        assert _is_transient_nav_error(Exception("net::ERR_CONNECTION_RESET at https://x")) is True

    def test_timeout_is_transient(self):
        assert _is_transient_nav_error(Exception("Timeout 25000ms exceeded")) is True

    def test_name_not_resolved_is_permanent(self):
        assert _is_transient_nav_error(Exception("net::ERR_NAME_NOT_RESOLVED")) is False


@pytest.mark.anyio
class TestGotoWithRetry:
    def _page(self, *side_effects):
        page = MagicMock()
        page.goto = AsyncMock(side_effect=list(side_effects))
        return page

    async def test_succeeds_after_transient_failures(self):
        # Two transient blips then success — completing past the await proves it retried.
        page = self._page(
            Exception("net::ERR_CONNECTION_RESET"),
            Exception("net::ERR_CONNECTION_RESET"),
            None,
        )
        result = await _goto_with_retry(page, "https://x.com", attempts=3, delay=0)
        assert result is None

    async def test_permanent_error_raises_without_retry(self):
        page = self._page(Exception("net::ERR_NAME_NOT_RESOLVED"))
        with pytest.raises(Exception, match="ERR_NAME_NOT_RESOLVED"):
            await _goto_with_retry(page, "https://x.com", attempts=3, delay=0)

    async def test_gives_up_after_attempts_exhausted(self):
        page = self._page(
            Exception("net::ERR_TIMED_OUT"),
            Exception("net::ERR_TIMED_OUT"),
            Exception("net::ERR_TIMED_OUT"),
        )
        with pytest.raises(Exception, match="ERR_TIMED_OUT"):
            await _goto_with_retry(page, "https://x.com", attempts=3, delay=0)
