"""Slash-command skills: a leading /<slug> invokes that skill, and the power-user
starter set is installed by default."""

from agent_space.runtime import skill_store


def test_slash_command_resolves_to_skill():
    skill = skill_store.resolve_command("/goal launch a podcast")
    assert skill is not None and skill.get("slug") == "goal"


def test_plain_message_is_not_a_command():
    assert skill_store.resolve_command("how do I launch a podcast?") is None


def test_unknown_command_resolves_to_nothing():
    assert skill_store.resolve_command("/definitely-not-a-skill hello") is None


def test_starter_skills_installed():
    slugs = {str(s.get("slug")) for s in skill_store.list_skills(limit=500)}
    assert {"goal", "ghost", "summarize", "critique", "rewrite"} <= slugs
