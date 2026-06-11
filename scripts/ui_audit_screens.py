"""One-shot UI audit: screenshot every route at phone + laptop widths.

Throwaway helper for a visual review pass — writes PNGs to .ui-audit/ (gitignored
tmp dir). Touch emulation is enabled for the phone profile so isMobile/touch
branches render the way a real phone sees them.
"""
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:5173"
OUT = Path(__file__).resolve().parent.parent / ".ui-audit"

ROUTES = [
    "/chat", "/atlas", "/builder", "/agents", "/self-code",
    "/settings", "/workflow", "/skills", "/automation",
    "/research", "/security", "/autonomy", "/dashboard",
    "/audit", "/notebook", "/agent-studio",
]

PROFILES = {
    "phone": {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True, "device_scale_factor": 2},
    "laptop": {"viewport": {"width": 1440, "height": 900}, "is_mobile": False, "has_touch": False, "device_scale_factor": 1},
}


async def main() -> int:
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for name, profile in PROFILES.items():
            ctx = await browser.new_context(**profile)
            page = await ctx.new_page()
            for route in ROUTES:
                slug = route.strip("/").replace("/", "_") or "root"
                try:
                    await page.goto(BASE + route, wait_until="networkidle", timeout=20000)
                except Exception:
                    # networkidle can starve on polling pages; settle and shoot anyway
                    await page.wait_for_timeout(1500)
                await page.wait_for_timeout(800)
                await page.screenshot(path=str(OUT / f"{name}_{slug}.png"), full_page=False)
                print(f"{name} {route} ok")
            await ctx.close()
        await browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
