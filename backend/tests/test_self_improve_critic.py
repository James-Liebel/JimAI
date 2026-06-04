import json
import pytest

from agent_space import self_improve_helpers as si


@pytest.mark.anyio
async def test_critic_prune_keeps_only_keep_verdict(monkeypatch):
    candidates = [
        {"title": "A", "acceptance": "ax"},
        {"title": "B", "acceptance": "bx"},
        {"title": "C", "acceptance": "cx"},
    ]
    ranked_payload = {
        "ranked": [
            {"title": "B", "scope_files": [], "acceptance": "bx",
             "scores": {"impact": 9, "specificity": 8, "testability": 8, "blast_radius": 9},
             "overall": 34, "verdict": "keep", "reason": "best"},
            {"title": "A", "scope_files": [], "acceptance": "ax",
             "scores": {"impact": 7, "specificity": 6, "testability": 7, "blast_radius": 7},
             "overall": 27, "verdict": "keep", "reason": "fine"},
            {"title": "C", "scope_files": [], "acceptance": "cx",
             "scores": {"impact": 3, "specificity": 4, "testability": 3, "blast_radius": 5},
             "overall": 15, "verdict": "drop", "reason": "too vague"},
        ]
    }

    async def fake_chat_full(**kwargs):
        return json.dumps(ranked_payload)

    monkeypatch.setattr(si.ollama_client, "chat_full", fake_chat_full)

    kept = await si._critic_prune(candidates, model="x", max_suggestions=5)
    titles = [k["title"] for k in kept]
    assert titles == ["B", "A"]


@pytest.mark.anyio
async def test_critic_prune_falls_back_to_input_on_failure(monkeypatch):
    async def fake_chat_full(**kwargs):
        raise RuntimeError("model down")

    monkeypatch.setattr(si.ollama_client, "chat_full", fake_chat_full)

    candidates = [{"title": "A"}, {"title": "B"}, {"title": "C"}]
    kept = await si._critic_prune(candidates, model="x", max_suggestions=2)
    assert kept == candidates[:2]


def test_candidates_to_strings_includes_scope_and_acceptance():
    out = si._candidates_to_strings([
        {"title": "Refactor X", "scope_files": ["a.py", "b.py"], "acceptance": "tests green"},
    ])
    assert len(out) == 1
    assert "Refactor X" in out[0]
    assert "a.py" in out[0]
    assert "tests green" in out[0]
