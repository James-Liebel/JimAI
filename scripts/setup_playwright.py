"""Install Playwright Python package (optional) and Chromium for JimAI browser tools."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_REQUIREMENTS = REPO_ROOT / "backend" / "requirements.txt"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--browser-only",
        action="store_true",
        help="Only run `playwright install chromium` (skip pip).",
    )
    parser.add_argument(
        "--skip-pip",
        action="store_true",
        help="Skip pip install (same as --browser-only for installs).",
    )
    args = parser.parse_args()
    py = sys.executable
    browser_only = bool(args.browser_only or args.skip_pip)

    if not browser_only:
        if not BACKEND_REQUIREMENTS.is_file():
            print(f"Missing {BACKEND_REQUIREMENTS}", file=sys.stderr)
            return 1
        pip = subprocess.run(
            [py, "-m", "pip", "install", "-r", str(BACKEND_REQUIREMENTS)],
            cwd=str(REPO_ROOT),
        )
        if pip.returncode != 0:
            return pip.returncode

    inst = subprocess.run(
        [py, "-m", "playwright", "install", "chromium"],
        cwd=str(REPO_ROOT),
    )
    return inst.returncode


if __name__ == "__main__":
    raise SystemExit(main())
