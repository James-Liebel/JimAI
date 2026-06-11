"""Re-shoot only the pages touched by the visual-fix pass (phone + laptop studio)."""
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:5173"
OUT = Path(__file__).resolve().parent.parent / ".ui-audit"

PHONE = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True, "device_scale_factor": 2}
LAPTOP = {"viewport": {"width": 1440, "height": 900}, "is_mobile": False, "has_touch": False, "device_scale_factor": 1}

SHOTS = [
    ("phone", "/chat", "v2_phone_chat"),
    ("phone", "/agents", "v2_phone_agents"),
    ("phone", "/skills", "v2_phone_skills"),
    ("phone", "/agent-studio", "v2_phone_agent-studio"),
    ("laptop", "/agent-studio", "v2_laptop_agent-studio"),
]


async def main() -> int:
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        contexts = {
            "phone": await browser.new_context(**PHONE),
            "laptop": await browser.new_context(**LAPTOP),
        }
        for profile, route, name in SHOTS:
            page = await contexts[profile].new_page()
            try:
                await page.goto(BASE + route, wait_until="networkidle", timeout=20000)
            except Exception:
                pass
            await page.wait_for_timeout(2500)  # let data fully load (agents roster)
            await page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
            await page.close()
            print(name, "ok")
        for ctx in contexts.values():
            await ctx.close()
        await browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
