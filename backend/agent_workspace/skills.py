"""Read/write skill markdown files under skills/<agent-slug>/."""

import time
from dataclasses import dataclass
from pathlib import Path

from agent_workspace.paths import SKILLS_ROOT
from agent_workspace.models import Agent


def _safe_slug(slug: str) -> str:
    if not slug or ".." in slug or "/" in slug or "\\" in slug:
        raise ValueError("Invalid slug")
    return slug


def agent_skills_dir(slug: str) -> Path:
    return SKILLS_ROOT / _safe_slug(slug)


def shared_skills_dir() -> Path:
    return SKILLS_ROOT / "shared"


@dataclass
class SkillInfo:
    name: str
    slug: str
    path: str
    preview: str
    modified_at: str
    size_bytes: int


def list_skills_for_agent(agent: Agent) -> list[SkillInfo]:
    d = agent_skills_dir(agent.slug)
    if not d.is_dir():
        return []
    out: list[SkillInfo] = []
    for p in sorted(d.glob("*.md")):
        stat = p.stat()
        text = p.read_text(encoding="utf-8", errors="replace")
        first_line = text.strip().split("\n")[0] if text.strip() else ""
        preview = first_line[:160] + ("…" if len(first_line) > 160 else "")
        out.append(
            SkillInfo(
                name=p.stem.replace("-", " ").replace("_", " ").title(),
                slug=p.stem,
                path=str(p.relative_to(SKILLS_ROOT)).replace("\\", "/"),
                preview=preview,
                modified_at=_mtime_iso(stat.st_mtime),
                size_bytes=stat.st_size,
            )
        )
    return out


def _mtime_iso(mtime: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(mtime))


def read_skill(agent_slug: str, skill_slug: str) -> str:
    p = agent_skills_dir(agent_slug) / f"{_safe_skill_file(skill_slug)}.md"
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return p.read_text(encoding="utf-8")


def write_skill(agent_slug: str, skill_slug: str, content: str) -> Path:
    d = agent_skills_dir(agent_slug)
    d.mkdir(parents=True, exist_ok=True)
    fname = f"{_safe_skill_file(skill_slug)}.md"
    p = d / fname
    p.write_text(content, encoding="utf-8")
    return p


def delete_skill(agent_slug: str, skill_slug: str) -> bool:
    p = agent_skills_dir(agent_slug) / f"{_safe_skill_file(skill_slug)}.md"
    if p.is_file():
        p.unlink()
        return True
    return False


def _safe_skill_file(name: str) -> str:
    base = Path(name).name
    if not base or ".." in name:
        raise ValueError("Invalid skill name")
    return Path(base).stem


def read_shared_skill_files(rel_paths: list[str]) -> str:
    parts: list[str] = []
    for rel in rel_paths:
        rel = rel.replace("\\", "/").lstrip("/")
        if ".." in rel:
            continue
        p = SKILLS_ROOT / rel
        if p.is_file() and p.suffix == ".md":
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n\n".join(parts)
