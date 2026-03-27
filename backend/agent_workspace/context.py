"""Build full system prompt with injected skill markdown."""

from pathlib import Path

from agent_workspace.models import Agent
from agent_workspace.paths import SKILLS_ROOT
from agent_workspace.skills import agent_skills_dir, read_shared_skill_files


def build_agent_context(agent: Agent, extra_shared_paths: list[str] | None = None) -> str:
    """
    Concatenate agent system prompt with all *.md in skills/<slug>/ and optional shared skills.
    """
    full_system = agent.system_prompt.strip()
    skills_text = ""

    skills_dir = agent_skills_dir(agent.slug)
    if skills_dir.exists():
        for skill_file in sorted(skills_dir.glob("*.md")):
            skill_name = skill_file.stem.replace("-", " ").replace("_", " ").title()
            body = skill_file.read_text(encoding="utf-8", errors="replace")
            skills_text += f"\n\n<skill name='{skill_name}'>\n"
            skills_text += body
            skills_text += "\n</skill>"

    if extra_shared_paths:
        shared_body = read_shared_skill_files(extra_shared_paths)
        if shared_body.strip():
            skills_text += "\n\n<shared_skills>\n" + shared_body + "\n</shared_skills>"

    if skills_text.strip():
        full_system += f"\n\n<available_skills>{skills_text}\n</available_skills>"
    return full_system
