"""Throwaway label linter: flags clipped, offscreen, and occluded text per route.

Geometry + hit-test stand-in for eyeballing screenshots — runs each route at the
iPhone 15 Plus viewport. elementsFromPoint filters out content that is merely
scrolled away inside an overflow container (not a real visual bug), and the
fixed bottom nav is excluded as an expected occluder of scrolling content.
"""
import asyncio
import json
import sys

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:5173"

ROUTES = [
    "/chat", "/atlas", "/builder", "/agents", "/self-code",
    "/settings", "/workflow", "/skills", "/automation",
    "/research", "/security", "/autonomy", "/dashboard",
    "/audit", "/notebook", "/agent-studio",
]

JS = r"""
() => {
  const issues = [];
  const vw = innerWidth, vh = innerHeight;
  function visible(el) {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || +s.opacity === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  }
  function isTextLeaf(el) {
    if (!visible(el)) return false;
    for (const n of el.childNodes) {
      if (n.nodeType === 3 && n.textContent.trim().length > 1) return true;
    }
    return false;
  }
  function label(el) {
    return (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 60);
  }
  function desc(el) {
    const cls = (typeof el.className === 'string' ? el.className : '').split(/\s+/).slice(0, 4).join('.');
    return el.tagName.toLowerCase() + (cls ? '.' + cls : '') + ' "' + label(el) + '"';
  }
  const leaves = [...document.querySelectorAll('body *')].filter(isTextLeaf);
  for (const el of leaves) {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    // only judge what intersects the viewport
    if (r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) continue;

    if ((r.right > vw + 1 && r.left >= 0) || (r.left < -1 && r.right <= vw)) {
      issues.push({ type: 'offscreen-x', el: desc(el), rect: [r.left | 0, r.top | 0, r.width | 0, r.height | 0] });
    }
    if (el.scrollWidth > el.clientWidth + 2 && s.whiteSpace === 'nowrap'
        && s.textOverflow !== 'ellipsis' && s.overflowX !== 'hidden') {
      issues.push({ type: 'clipped-nowrap', el: desc(el), sw: el.scrollWidth, cw: el.clientWidth });
    }

    // occlusion hit-test at the text's center
    const cx = Math.min(vw - 2, Math.max(2, r.left + r.width / 2));
    const cy = Math.min(vh - 2, Math.max(2, r.top + r.height / 2));
    const stack = document.elementsFromPoint(cx, cy);
    const idx = stack.findIndex((e) => e === el || el.contains(e));
    if (idx === -1) continue; // clipped by ancestor overflow → just scrolled away
    for (let k = 0; k < idx; k++) {
      const above = stack[k];
      if (above.contains(el) || el.contains(above)) continue;
      if (above.closest('nav')) break; // fixed bottom nav over scroll content: expected
      const sa = getComputedStyle(above);
      if (sa.pointerEvents === 'none') continue;
      if (!(sa.backgroundColor && sa.backgroundColor !== 'rgba(0, 0, 0, 0)') && !above.textContent.trim()) continue;
      issues.push({ type: 'occluded', el: desc(el), by: desc(above) });
      break;
    }
  }
  return issues;
}
"""


async def main() -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(
            viewport={"width": 430, "height": 932}, is_mobile=True,
            has_touch=True, device_scale_factor=1,
        )
        page = await ctx.new_page()
        for route in ROUTES:
            try:
                await page.goto(BASE + route, wait_until="networkidle", timeout=20000)
            except Exception:
                await page.wait_for_timeout(1500)
            await page.wait_for_timeout(1200)
            issues = await page.evaluate(JS)
            seen = set()
            uniq = []
            for it in issues:
                key = json.dumps(it, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    uniq.append(it)
            if uniq:
                print(f"\n=== {route} ({len(uniq)} issues) ===")
                for it in uniq[:20]:
                    print(" ", json.dumps(it, ensure_ascii=False))
        await browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
