"""Exit 0 if Playwright can launch Chromium; else 1. Used by agentspace_lifecycle."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
