#!/usr/bin/env python3
"""Print a tree of skill markdown files with sizes and mtimes."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"


def main() -> None:
    if not SKILLS.is_dir():
        print("No skills directory", file=sys.stderr)
        sys.exit(1)
    for p in sorted(SKILLS.rglob("*.md")):
        rel = p.relative_to(SKILLS)
        st = p.stat()
        print(f"{rel}  {st.st_size} bytes  mtime={int(st.st_mtime)}")


if __name__ == "__main__":
    main()
