"""Paths for agent workspace persistence and skills directory."""

from pathlib import Path

# private-ai/ (repo root containing backend/, frontend/, skills/)
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
DATA_DIR: Path = PROJECT_ROOT / "data" / "agent_workspace"
AGENTS_FILE: Path = DATA_DIR / "agents.json"
TEAMS_FILE: Path = DATA_DIR / "teams.json"
SKILLS_ROOT: Path = PROJECT_ROOT / "skills"
AGENTS_MD: Path = PROJECT_ROOT / "AGENTS.md"
