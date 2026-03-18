"""Screenshot helper — capture full-page screenshots of a URL using Playwright."""

import base64
import os
import uuid
from pathlib import Path

from playwright.async_api import async_playwright


async def capture_screenshots(url: str, max_images: int = 1) -> list[str]:
    """Capture one or more full-page screenshots of a URL.

    Returns a list of base64-encoded PNG images.
    """
    # Where to stash temporary screenshots (not exposed directly)
    out_dir = Path(os.getenv("WEBSHOT_DIR", "webshots"))
    out_dir.mkdir(parents=True, exist_ok=True)

    images_b64: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 720})

        await page.goto(url, wait_until="networkidle", timeout=30000)

        for _ in range(max_images):
            filename = out_dir / f"shot-{uuid.uuid4().hex}.png"
            await page.screenshot(path=str(filename), full_page=True)
            with open(filename, "rb") as f:
                images_b64.append(base64.b64encode(f.read()).decode("utf-8"))

        await browser.close()

    return images_b64

