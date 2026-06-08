"""Tests for the local fine-tuning subsystem (training/)."""

from __future__ import annotations

from pathlib import Path

from training import dataset as ds
from training import recipe as rc
from training.catalog import TrainMethod, all_models, roles_for_model, trainable_models
from training.modelfile import render_modelfile, trained_tag
from training.pipeline import prepare_model


# ── catalog ────────────────────────────────────────────────────────────────

def test_all_models_includes_primary_chat_model():
    models = {entry.model for entry in all_models()}
    assert "qwen3:8b" in models


def test_embedding_model_classified_as_embedding_not_text_lora():
    embed = next(e for e in all_models() if e.model == "nomic-embed-text")
    assert embed.method is TrainMethod.EMBEDDING


def test_vision_model_classified_as_vision_lora():
    vision = next(e for e in all_models() if e.model == "qwen2.5vl:7b")
    assert vision.method is TrainMethod.VISION_LORA


def test_trainable_text_models_exclude_embeddings_and_vision():
    text_models = {e.model for e in trainable_models(TrainMethod.TEXT_LORA)}
    assert "nomic-embed-text" not in text_models
    assert "qwen2.5vl:7b" not in text_models
    assert "qwen3:8b" in text_models


def test_roles_for_model_reports_chat_role():
    assert "chat" in roles_for_model("qwen3:8b")


# ── dataset (pure transforms) ───────────────────────────────────────────────

def test_transcripts_to_sft_pairs_user_then_assistant():
    transcript = [
        {"role": "user", "content": "hi", "mode": "chat"},
        {"role": "assistant", "content": "hello", "mode": "chat"},
    ]
    examples = ds.transcripts_to_sft([transcript])
    roles = [m["role"] for m in examples[0]["messages"]]
    assert roles[-2:] == ["user", "assistant"]


def test_transcripts_to_sft_skips_empty_assistant_turns():
    transcript = [
        {"role": "user", "content": "hi", "mode": "chat"},
        {"role": "assistant", "content": "   ", "mode": "chat"},
    ]
    assert ds.transcripts_to_sft([transcript]) == []


def test_reviews_to_dpo_pairs_approved_against_rejected_same_run():
    reviews = [
        {"run_id": "r1", "status": "approved", "objective": "fix bug", "diff": "good"},
        {"run_id": "r1", "status": "rejected", "objective": "fix bug", "diff": "bad"},
    ]
    pairs = ds.reviews_to_dpo(reviews)
    assert pairs == [{"prompt": "fix bug", "chosen": "good", "rejected": "bad"}]


def test_reviews_to_dpo_drops_runs_without_both_sides():
    reviews = [{"run_id": "r1", "status": "approved", "objective": "x", "diff": "y"}]
    assert ds.reviews_to_dpo(reviews) == []


def test_write_jsonl_returns_row_count(tmp_path: Path):
    count = ds.write_jsonl(tmp_path / "out.jsonl", [{"a": 1}, {"a": 2}])
    assert count == 2


# ── modelfile ────────────────────────────────────────────────────────────────

def test_render_modelfile_includes_base_and_adapter():
    text = render_modelfile("qwen3:8b", adapter_path="/x/gguf", temperature=0.7)
    assert "FROM qwen3:8b" in text
    assert "ADAPTER /x/gguf" in text


def test_trained_tag_prefixes_without_clobbering_base_tag():
    assert trained_tag("qwen3:8b") == "jimai-qwen3:8b"


# ── recipe ───────────────────────────────────────────────────────────────────

def test_render_training_script_substitutes_all_placeholders():
    cfg = rc.RecipeConfig(
        model="qwen3:8b", hf_repo="Qwen/Qwen3-8B",
        sft_path="/x/sft.jsonl", dpo_path=None, output_dir="/x/out",
    )
    script = rc.render_training_script(cfg)
    assert "@@" not in script
    assert "Qwen/Qwen3-8B" in script


def test_render_training_script_omits_dpo_path_when_none():
    cfg = rc.RecipeConfig(
        model="qwen3:8b", hf_repo="Qwen/Qwen3-8B",
        sft_path="/x/sft.jsonl", dpo_path=None, output_dir="/x/out",
    )
    assert "DPO_PATH = None" in rc.render_training_script(cfg)


# ── pipeline ─────────────────────────────────────────────────────────────────

def test_prepare_model_writes_script_and_modelfile(tmp_path: Path):
    entry = next(e for e in all_models() if e.model == "qwen3:8b")
    examples = [{"messages": [{"role": "user", "content": "hi"},
                              {"role": "assistant", "content": "yo"}], "mode": "chat"}]
    result = prepare_model(entry, tmp_path, sft_examples=examples, dpo_pairs=[])
    assert result.script_path.exists()
    assert result.modelfile_path.exists()
    assert result.sft_count == 1


def test_prepare_model_skips_vision_with_reason(tmp_path: Path):
    entry = next(e for e in all_models() if e.model == "qwen2.5vl:7b")
    result = prepare_model(entry, tmp_path, sft_examples=[], dpo_pairs=[])
    assert result.skipped
