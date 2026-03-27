"""Basic browser-oriented helpers."""

from __future__ import annotations

import webbrowser

from tools.screenshot import capture_screenshots


def open_url(url: str) -> dict:
    """Open a URL in the default browser."""
    webbrowser.open(url)
    return {"url": url, "opened": True}


async def capture_page(url: str, max_images: int = 1) -> dict:
    """Capture one or more screenshots of a web page."""
    images = await capture_screenshots(url, max_images=max_images)
    return {"url": url, "images": images, "count": len(images)}
