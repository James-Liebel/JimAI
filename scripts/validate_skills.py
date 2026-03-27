#!/usr/bin/env python3
"""Verify agent/team referenced skill paths exist; list orphan skill files."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
AGENTS_JSON = ROOT / "data" / "agent_workspace" / "agents.json"
TEAMS_JSON = ROOT / "data" / "agent_workspace" / "teams.json"


def main() -> None:
    referenced: set[str] = set()
    if TEAMS_JSON.is_file():
        data = json.loads(TEAMS_JSON.read_text(encoding="utf-8"))
        for t in data.get("teams", []):
            for p in t.get("shared_skills", []) or []:
                referenced.add(p.replace("\\", "/").lstrip("/"))

    on_disk: set[str] = set()
    if SKILLS.is_dir():
        for p in SKILLS.rglob("*.md"):
            on_disk.add(p.relative_to(SKILLS).as_posix())

    missing = sorted(p for p in referenced if p and not (SKILLS / p).is_file())
    orphans = sorted(f for f in on_disk if f not in referenced and not f.startswith("shared/"))
    # shared/* and per-agent dirs are not always referenced in JSON — treat orphans as unreferenced non-shared only
    orphans = [f for f in on_disk if f not in referenced]

    print("Referenced paths missing on disk:")
    for m in missing:
        print(f"  MISSING {m}")
    if not missing:
        print("  (none)")

    print("\nFiles on disk not listed in team shared_skills (informational):")
    for o in orphans[:200]:
        if o != "README.md":
            print(f"  {o}")
    if len(orphans) > 200:
        print(f"  ... and {len(orphans) - 200} more")

    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
