"""Generate SKILL.md content via local Ollama."""

from models import ollama_client


SKILL_GEN_TEMPLATE = """You are a skill documentation writer for an AI agent named {agent_name} whose role is {agent_role}.

Your job is to write a SKILL.md file that will be injected into this agent's context before every run.
A SKILL.md file teaches the agent HOW to do something — it's a set of best practices, frameworks,
checklists, decision rules, and examples that help the agent perform a specific capability well.

Write a SKILL.md for the skill: "{skill_name}"
Description: "{skill_description}"

The SKILL.md should:
- Start with a one-paragraph summary of what this skill is and when to use it
- Include concrete step-by-step processes or frameworks
- Include decision rules ("if X, then Y")
- Include quality checklists where applicable
- Include 1-2 brief examples of good vs bad outputs
- Be written in second person ("You should...", "When reviewing...")
- Be concise but complete — aim for 300-600 words
- Use markdown headers and bullet points for readability

{example_block}

Output ONLY the markdown content. No preamble, no explanation, no code fences."""


async def generate_skill_markdown(
    agent_name: str,
    agent_role: str,
    skill_name: str,
    skill_description: str,
    example_task: str | None,
    model: str = "qwen3:8b",
) -> str:
    example_block = ""
    if example_task and example_task.strip():
        example_block = (
            "Use this real task or example to extract reusable patterns:\n"
            f"---\n{example_task.strip()}\n---\n"
        )
    prompt = SKILL_GEN_TEMPLATE.format(
        agent_name=agent_name,
        agent_role=agent_role,
        skill_name=skill_name,
        skill_description=skill_description or "(infer from skill name)",
        example_block=example_block,
    )
    parts: list[str] = []
    async for chunk in ollama_client.generate(
        model=model,
        prompt=prompt,
        system="You write concise, actionable skill documentation. Output markdown only.",
        stream=True,
        temperature=0.4,
        num_ctx=8192,
    ):
        parts.append(chunk)
    text = "".join(parts).strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text
