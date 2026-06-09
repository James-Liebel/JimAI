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


# ── external data sources (pure converters, no network) ──────────────────────

def test_alpaca_converter_joins_instruction_and_input():
    from training.sources import _alpaca

    user, assistant = _alpaca({"instruction": "Sort a list", "input": "[3,1,2]", "output": "sorted"})
    assert user == "Sort a list\n\n[3,1,2]"
    assert assistant == "sorted"


def test_gsm8k_converter_maps_question_and_answer():
    from training.sources import _gsm8k

    user, assistant = _gsm8k({"question": "2+2?", "answer": "4"})
    assert (user, assistant) == ("2+2?", "4")


def test_sources_cover_core_roles():
    from training.sources import SOURCES

    assert {"code", "math", "finance", "chat"} <= set(SOURCES)


# ── external data merges into the build path ─────────────────────────────────

def test_read_jsonl_round_trips_written_rows(tmp_path: Path):
    path = tmp_path / "rows.jsonl"
    rows = [{"messages": [{"role": "user", "content": "hi"}], "mode": "code"}]
    ds.write_jsonl(path, rows)
    assert ds.read_jsonl(path) == rows


def test_read_jsonl_missing_file_yields_no_rows(tmp_path: Path):
    assert ds.read_jsonl(tmp_path / "absent.jsonl") == []


def test_load_external_sft_combines_role_files_in_filename_order(tmp_path: Path):
    ds.write_jsonl(tmp_path / "code.jsonl", [{"messages": [], "mode": "code"}])
    ds.write_jsonl(tmp_path / "math.jsonl", [{"messages": [], "mode": "math"}])
    assert ds.load_external_sft(tmp_path) == [
        {"messages": [], "mode": "code"},
        {"messages": [], "mode": "math"},
    ]


def test_load_external_sft_missing_dir_yields_no_examples(tmp_path: Path):
    assert ds.load_external_sft(tmp_path / "absent") == []


def test_external_sft_reaches_a_model_through_prepare(tmp_path: Path):
    sources = tmp_path / "sources"
    ds.write_jsonl(sources / "code.jsonl", [{"messages": [], "mode": "code"}])
    entry = next(
        e for e in trainable_models(TrainMethod.TEXT_LORA)
        if "code" in roles_for_model(e.model) and rc.hf_repo_for(e.model)
    )
    result = prepare_model(
        entry, tmp_path,
        sft_examples=ds.load_external_sft(sources),
        dpo_pairs=[],
    )
    assert result.sft_count == 1
