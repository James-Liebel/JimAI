"""Tests for the autonomy primitives.

Covers logic that does not require a live Ollama service: data persistence,
patch application, lesson retrieval by token overlap, and heartbeat job
scheduling. Embedding-dependent paths are exercised through a stub embed
function so the tests don't depend on the network.

Run:
    cd backend
    pytest tests/test_autonomy.py -v
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agent_space.autonomy.episodic_memory import EpisodicMemory, EpisodeRecord
from agent_space.autonomy.heartbeat import HeartbeatJob, HeartbeatScheduler
from agent_space.autonomy.reflection import ReflectionEngine, ReflectionTrace
from agent_space.autonomy.replan import ReplanDecision, ReplanEngine
from agent_space.autonomy.skill_library import SkillLibrary


# ---------------------------------------------------------------- helpers


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def tmp_episodes_path(tmp_path: Path) -> Path:
    return tmp_path / "episodes.jsonl"


@pytest.fixture
def tmp_skill_path(tmp_path: Path) -> Path:
    return tmp_path / "skills.jsonl"


@pytest.fixture
def tmp_reflections_path(tmp_path: Path) -> Path:
    return tmp_path / "reflections.jsonl"


@pytest.fixture
def tmp_jobs_path(tmp_path: Path) -> Path:
    return tmp_path / "jobs.json"


# ------------------------------------------------------ EpisodicMemory


class TestEpisodicMemory:
    def test_record_persists_to_disk_without_embed(self, tmp_episodes_path: Path):
        async def _go():
            mem = EpisodicMemory(file_path=tmp_episodes_path)
            await mem.record(
                run_id="r1",
                agent_id="planner",
                event="run_completed",
                outcome="success",
                summary="planned and executed cleanly",
                embed=False,
            )
            return mem

        mem = asyncio.run(_go())
        assert tmp_episodes_path.exists()
        rows = mem.list_recent(limit=10)
        assert len(rows) == 1
        assert rows[0].run_id == "r1"
        assert rows[0].outcome == "success"

    def test_list_by_run_filters_correctly(self, tmp_episodes_path: Path):
        async def _go():
            mem = EpisodicMemory(file_path=tmp_episodes_path)
            await mem.record(run_id="r1", agent_id="a", event="step", outcome="ok", summary="x", embed=False)
            await mem.record(run_id="r2", agent_id="a", event="step", outcome="ok", summary="y", embed=False)
            await mem.record(run_id="r1", agent_id="a", event="step", outcome="ok", summary="z", embed=False)
            return mem

        mem = asyncio.run(_go())
        for_r1 = mem.list_by_run("r1")
        for_r2 = mem.list_by_run("r2")
        assert {r.summary for r in for_r1} == {"x", "z"}
        assert {r.summary for r in for_r2} == {"y"}

    def test_stats_reports_counts(self, tmp_episodes_path: Path):
        async def _go():
            mem = EpisodicMemory(file_path=tmp_episodes_path)
            for i in range(3):
                await mem.record(
                    run_id=f"r{i}", agent_id="a", event="step", outcome="ok", summary=f"s{i}", embed=False
                )
            return mem.stats()

        stats = asyncio.run(_go())
        assert stats["count"] == 3
        assert stats["embedded"] == 0
        assert stats["runs"] == 3


# ------------------------------------------------------ SkillLibrary


class TestSkillLibrary:
    def test_capture_and_token_overlap_retrieve(self, tmp_skill_path: Path):
        async def _embed_stub(_text: str):
            return None  # force token-overlap fallback

        async def _go():
            lib = SkillLibrary(file_path=tmp_skill_path, embed_fn=_embed_stub)
            await lib.capture(
                name="export-research",
                description="export web research results to file",
                objective="produce structured research export with citations",
                artifact="def export(): ...",
                artifact_type="code",
                tags=["research", "export", "citations"],
            )
            return lib

        lib = asyncio.run(_go())

        async def _retrieve():
            return await lib.retrieve("how to export research findings", limit=5, min_score=0.0)

        hits = asyncio.run(_retrieve())
        assert len(hits) == 1
        entry, score = hits[0]
        assert entry.name == "export-research"
        assert score >= 0.0  # should hit on token overlap

    def test_capture_merges_existing_by_name(self, tmp_skill_path: Path):
        async def _go():
            lib = SkillLibrary(file_path=tmp_skill_path, embed_fn=None)
            await lib.capture(name="x", description="d", objective="o", artifact="A")
            await lib.capture(name="X", description="d2", objective="o", artifact="AA")
            return lib

        lib = asyncio.run(_go())
        rows = lib.list_all()
        assert len(rows) == 1
        assert rows[0].success_count == 2
        # Larger artifact should be preserved.
        assert rows[0].artifact == "AA"

    def test_render_for_prompt_caps_chars(self, tmp_skill_path: Path):
        async def _go():
            lib = SkillLibrary(file_path=tmp_skill_path, embed_fn=None)
            await lib.capture(name="big", description="d", objective="o", artifact="x" * 5000)
            return lib

        lib = asyncio.run(_go())
        rows = lib.list_all()
        rendered = SkillLibrary.render_for_prompt([(rows[0], 0.9)], max_chars=400)
        assert len(rendered) <= 400 + 200  # block size bounded


# ------------------------------------------------------ ReflectionEngine


class TestReflectionEngine:
    def test_lessons_for_token_overlap(self, tmp_reflections_path: Path):
        engine = ReflectionEngine(file_path=tmp_reflections_path)
        # Manually inject traces so we don't call the LLM.
        tr1 = ReflectionTrace(
            id="a", created_at=time.time(), run_id="r1", agent_id="planner",
            objective="export research findings as markdown",
            attempt=1, failure_reason="formatter crashed",
            lesson="Use safe formatter; sanitize bullet markers.",
        )
        tr2 = ReflectionTrace(
            id="b", created_at=time.time(), run_id="r2", agent_id="planner",
            objective="run integration tests for shopping cart",
            attempt=1, failure_reason="timeout",
            lesson="Increase timeout; check db state.",
        )
        with tmp_reflections_path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(tr1.to_dict()) + "\n")
            fh.write(json.dumps(tr2.to_dict()) + "\n")

        results = engine.lessons_for("export research data to markdown", limit=5)
        assert len(results) == 1
        assert results[0].id == "a"

    def test_render_for_prompt(self, tmp_reflections_path: Path):
        tr = ReflectionTrace(
            id="a", created_at=time.time(), run_id="r1", agent_id="planner",
            objective="o", attempt=2, failure_reason="x", lesson="be careful",
        )
        rendered = ReflectionEngine.render_for_prompt([tr])
        assert "Lessons" in rendered
        assert "be careful" in rendered


# ------------------------------------------------------ ReplanEngine


class TestReplanEngine:
    def test_apply_drop_patch(self):
        plan = [{"task": "a"}, {"task": "b"}, {"task": "c"}]
        new_plan = ReplanEngine.apply_patches(plan, [{"op": "drop", "task_index": 1}])
        assert [p["task"] for p in new_plan] == ["a", "c"]

    def test_apply_replace_patch(self):
        plan = [{"task": "a"}, {"task": "b"}]
        new_plan = ReplanEngine.apply_patches(
            plan, [{"op": "replace", "task_index": 1, "task": {"task": "B!"}}]
        )
        assert new_plan[1]["task"] == "B!"

    def test_apply_insert_after_patch(self):
        plan = [{"task": "a"}, {"task": "c"}]
        new_plan = ReplanEngine.apply_patches(
            plan, [{"op": "insert_after", "task_index": 0, "task": {"task": "b"}}]
        )
        assert [p["task"] for p in new_plan] == ["a", "b", "c"]

    def test_multiple_patches_applied_in_reverse_index_order(self):
        plan = [{"task": "a"}, {"task": "b"}, {"task": "c"}]
        new_plan = ReplanEngine.apply_patches(
            plan,
            [
                {"op": "drop", "task_index": 0},
                {"op": "insert_after", "task_index": 2, "task": {"task": "d"}},
            ],
        )
        # drop a, insert after index 2 -> b, c, d
        assert [p["task"] for p in new_plan] == ["b", "c", "d"]

    def test_decision_fallback_on_max_replans(self):
        engine = ReplanEngine(max_replans=2)
        decision = asyncio.run(
            engine.evaluate(
                objective="x", plan=[], completed=[], last_result=None, replans_used=2
            )
        )
        assert isinstance(decision, ReplanDecision)
        assert decision.decision == "continue"
        assert "budget" in decision.reason.lower()


# ------------------------------------------------------ HeartbeatScheduler


class TestHeartbeatScheduler:
    def test_add_and_list_jobs(self, tmp_jobs_path: Path):
        captured: list[HeartbeatJob] = []

        async def _action(job: HeartbeatJob):
            captured.append(job)
            return {"id": "x"}

        sched = HeartbeatScheduler(action=_action, file_path=tmp_jobs_path, tick_interval_seconds=5)

        async def _go():
            job = await sched.add_job(
                name="nightly",
                objective="reflect on yesterday",
                interval_seconds=120,
                first_fire_in_seconds=30,
            )
            return job

        job = asyncio.run(_go())
        assert job.name == "nightly"
        rows = sched.list_jobs()
        assert len(rows) == 1
        assert rows[0].interval_seconds == 120

    def test_tick_fires_due_jobs(self, tmp_jobs_path: Path):
        fired: list[str] = []

        async def _action(job: HeartbeatJob):
            fired.append(job.id)
            return None

        sched = HeartbeatScheduler(action=_action, file_path=tmp_jobs_path, tick_interval_seconds=5)

        async def _go():
            job = await sched.add_job(
                name="immediate",
                objective="x",
                interval_seconds=60,
                first_fire_in_seconds=0,
            )
            return job

        job = asyncio.run(_go())

        async def _tick():
            return await sched.tick()

        result = asyncio.run(_tick())
        assert result["fired"] == 1
        assert fired == [job.id]

    def test_tick_respects_not_yet_due(self, tmp_jobs_path: Path):
        async def _action(job: HeartbeatJob):
            return None

        sched = HeartbeatScheduler(action=_action, file_path=tmp_jobs_path, tick_interval_seconds=5)

        async def _go():
            await sched.add_job(
                name="future",
                objective="x",
                interval_seconds=120,
                first_fire_in_seconds=300,
            )
            return await sched.tick()

        result = asyncio.run(_go())
        assert result["fired"] == 0
        assert result["due"] == 0

    def test_one_shot_job_removed_after_firing(self, tmp_jobs_path: Path):
        async def _action(job: HeartbeatJob):
            return None

        sched = HeartbeatScheduler(action=_action, file_path=tmp_jobs_path, tick_interval_seconds=5)

        async def _go():
            await sched.schedule_self(
                agent_id="a",
                objective="follow up later",
                when_in_seconds=0,
            )
            return await sched.tick()

        result = asyncio.run(_go())
        assert result["fired"] == 1
        assert sched.list_jobs() == []

    def test_status_reflects_running_state(self, tmp_jobs_path: Path):
        async def _action(_job: HeartbeatJob):
            return None

        sched = HeartbeatScheduler(action=_action, file_path=tmp_jobs_path, tick_interval_seconds=5)
        status = sched.status()
        assert status["running"] is False
        assert status["job_count"] == 0
