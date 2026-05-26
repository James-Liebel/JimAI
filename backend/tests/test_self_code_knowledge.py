"""Self-improve coding-knowledge store: seed, persist, cap, and prompt injection.

KNOWLEDGE_FILE is redirected to a tmp path so these never read or write the real
data directory.
"""

import pytest

from agent_space import knowledge_store
from config.role_prompts import SELF_IMPROVE_FILE_REWRITE


@pytest.fixture
def temp_knowledge(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_store, "KNOWLEDGE_FILE", tmp_path / "coding_knowledge.md")


def test_get_seeds_default_when_file_missing(temp_knowledge):
    assert "Local-first" in knowledge_store.get_knowledge()


def test_get_returns_previously_saved_content(temp_knowledge):
    knowledge_store.set_knowledge("Use pathlib, never os.path.")
    assert knowledge_store.get_knowledge() == "Use pathlib, never os.path."


def test_set_caps_at_max_chars(temp_knowledge):
    saved = knowledge_store.set_knowledge("x" * (knowledge_store.MAX_KNOWLEDGE_CHARS + 500))
    assert len(saved) == knowledge_store.MAX_KNOWLEDGE_CHARS


def test_prompt_block_includes_saved_knowledge(temp_knowledge):
    knowledge_store.set_knowledge("Prefer extending existing patterns.")
    assert "Prefer extending existing patterns." in knowledge_store.knowledge_prompt_block()


def test_prompt_block_is_empty_when_knowledge_blank(temp_knowledge):
    knowledge_store.set_knowledge("")
    assert knowledge_store.knowledge_prompt_block() == ""


def test_file_rewrite_prompt_enforces_file_only_output():
    assert "Return ONLY the complete, updated file content" in SELF_IMPROVE_FILE_REWRITE


async def _capture_rewrite_system_prompt(monkeypatch) -> str:
    """Run the self-improve file rewrite with a mocked model, returning the system prompt."""
    from agent_space import orchestrator as orch_mod

    captured: dict[str, str] = {}

    async def fake_chat_full(*, model, messages, temperature):
        captured["system"] = messages[0]["content"]
        return "new content line\n" * 6  # long enough to clear the truncation guardrail

    monkeypatch.setattr(orch_mod.ollama_client, "chat_full", fake_chat_full)
    # The method uses no instance state beyond the _strip_code_fence staticmethod,
    # so bypass the dependency-heavy __init__.
    orch = object.__new__(orch_mod.AgentSpaceOrchestrator)
    await orch._rewrite_file_for_self_improve(
        rel_path="backend/foo.py",
        current_content="def foo():\n    return 1\n" * 10,
        objective="o",
        prompt="p",
        confirmed_suggestions=["x"],
        focus="f",
        model="m",
    )
    return captured["system"]


@pytest.mark.anyio
async def test_file_rewrite_system_prompt_carries_coder_standards(temp_knowledge, monkeypatch):
    system = await _capture_rewrite_system_prompt(monkeypatch)
    assert "Return ONLY the complete, updated file content" in system


@pytest.mark.anyio
async def test_file_rewrite_system_prompt_injects_knowledge(temp_knowledge, monkeypatch):
    knowledge_store.set_knowledge("ALWAYS prefer anyio for async tests.")
    system = await _capture_rewrite_system_prompt(monkeypatch)
    assert "ALWAYS prefer anyio for async tests." in system


@pytest.mark.anyio
async def test_knowledge_endpoint_get_reflects_post(temp_knowledge):
    from agent_space import api

    await api.self_improve_set_knowledge(api.SelfImproveKnowledgeRequest(knowledge="# K\nuse pathlib"))
    got = await api.self_improve_get_knowledge()
    assert got["knowledge"] == "# K\nuse pathlib"
