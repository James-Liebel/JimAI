"""Tests for SkillStore's mtime-aware read cache.

``_read_skill`` skips the disk read + frontmatter parse when neither SKILL.md
nor skill.json has changed since the last load. These tests verify that the
cache is both effective (unchanged file → cached value) and correct (changed
file → fresh parse), so the optimisation never serves stale skill content.

Run:
    cd backend
    pytest tests/test_skill_store.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import agent_space.skill_store as skill_store_mod
from agent_space.skill_store import SkillStore

_SKILL_MD = "---\nname: Demo\ndescription: first\n---\n{body}"


class TestReadSkillCache:
    def _store_with_skill(self, tmp_path, monkeypatch) -> tuple[SkillStore, Path, float]:
        # Isolate the store on a temp skills dir and skip the heavy default install.
        monkeypatch.setattr(skill_store_mod, "SKILLS_DIR", tmp_path)
        monkeypatch.setattr(SkillStore, "install_default_skills", lambda self: [])
        store = SkillStore(settings_store=MagicMock())

        skill_dir = tmp_path / "demo"
        skill_dir.mkdir()
        md = skill_dir / "SKILL.md"
        md.write_text(_SKILL_MD.format(body="Body A"), encoding="utf-8")
        store._read_skill("demo")  # prime the cache
        return store, md, md.stat().st_mtime

    def test_serves_cache_when_mtime_unchanged(self, tmp_path, monkeypatch):
        store, md, mtime0 = self._store_with_skill(tmp_path, monkeypatch)
        # Rewrite content but pin mtime back — fingerprint unchanged → cached value.
        md.write_text(_SKILL_MD.format(body="Body B"), encoding="utf-8")
        os.utime(md, (mtime0, mtime0))
        assert "Body A" in store._read_skill("demo")["content"]

    def test_reparses_when_mtime_changes(self, tmp_path, monkeypatch):
        store, md, mtime0 = self._store_with_skill(tmp_path, monkeypatch)
        md.write_text(_SKILL_MD.format(body="Body B"), encoding="utf-8")
        os.utime(md, (mtime0 + 10, mtime0 + 10))
        assert "Body B" in store._read_skill("demo")["content"]

    def test_missing_skill_drops_stale_cache_entry(self, tmp_path, monkeypatch):
        store, md, _ = self._store_with_skill(tmp_path, monkeypatch)
        md.unlink()
        assert store._read_skill("demo") is None
