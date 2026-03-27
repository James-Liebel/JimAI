#!/usr/bin/env python3
"""
Generate default SKILL.md files for built-in agent slugs using local Ollama.

Usage:
  python scripts/generate_default_skills.py
  python scripts/generate_default_skills.py --force
  python scripts/generate_default_skills.py --agent coder
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))


DEFAULT_SETS: dict[str, list[tuple[str, str]]] = {
    "planner": [
        ("task-decomposition", "How to break large tasks into ordered subtasks with clear outcomes"),
        ("dependency-mapping", "How to identify and sequence dependencies between subtasks"),
        ("risk-assessment", "How to flag risks, assumptions, and mitigations in a plan"),
    ],
    "coder": [
        ("code-review", "Systematic code review for quality, bugs, and improvement opportunities"),
        ("refactoring", "When and how to refactor safely with small steps"),
        ("debugging", "Methodical debugging from reproduction to root cause"),
        ("test-writing", "How to write meaningful automated tests"),
    ],
    "researcher": [
        ("multi-source-search", "Search strategy and query formulation across sources"),
        ("source-evaluation", "Assessing source quality, bias, and credibility"),
        ("synthesis", "Combining findings into coherent, attributed summaries"),
    ],
    "verifier": [
        ("fact-checking", "Verifying claims and spotting unsupported statements"),
        ("logic-review", "Checking reasoning chains for errors and gaps"),
        ("completeness-check", "Ensuring important cases and edge conditions are covered"),
    ],
    "orchestrator": [
        ("delegation", "Assigning tasks to the right specialist agent"),
        ("synthesis", "Combining multi-agent outputs into one deliverable"),
        ("conflict-resolution", "Handling disagreements or contradictions between agents"),
    ],
}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Overwrite existing skill files")
    parser.add_argument("--agent", type=str, default=None, help="Only this agent slug")
    args = parser.parse_args()

    from agent_workspace.generator import generate_skill_markdown
    from agent_workspace.paths import SKILLS_ROOT

    agents_filter = [args.agent] if args.agent else list(DEFAULT_SETS.keys())

    for slug in agents_filter:
        if slug not in DEFAULT_SETS:
            print(f"Unknown agent slug: {slug}", file=sys.stderr)
            continue
        out_dir = SKILLS_ROOT / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        for skill_slug, description in DEFAULT_SETS[slug]:
            path = out_dir / f"{skill_slug}.md"
            if path.exists() and not args.force:
                print(f"skip exists: {path}")
                continue
            print(f"generating {path} ...")
            md = await generate_skill_markdown(
                agent_name=slug.replace("-", " ").title(),
                agent_role=slug,
                skill_name=skill_slug.replace("-", " ").title(),
                skill_description=description,
                example_task=None,
                model="qwen3:8b",
            )
            path.write_text(md, encoding="utf-8")
            print(f"wrote {path}")


if __name__ == "__main__":
    asyncio.run(main())
