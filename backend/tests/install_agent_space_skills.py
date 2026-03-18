"""Install and verify Agent Space default skills on disk.

Purpose: generate advanced SKILL.md files into data/agent_space/skills.
Date: 2026-03-11
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agent_space.config import SettingsStore
from agent_space.paths import SKILLS_DIR
from agent_space.skill_store import SkillStore


def main() -> None:
    store = SkillStore(settings_store=SettingsStore())
    installed = store.install_default_skills()
    print(f"installed_count={len(installed)}")
    print(f"skills_dir={SKILLS_DIR}")
    sample = store.list_skills(limit=8)
    print("sample=", [row.get("slug") for row in sample])


if __name__ == "__main__":
    main()
