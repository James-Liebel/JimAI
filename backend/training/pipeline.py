"""Orchestrate dataset → recipe → Modelfile for one model or the whole stack.

For each trainable model this prepares everything needed to train and reload it:
per-role SFT data, shared DPO pairs, a runnable training script, and a Modelfile
pointing at the adapter the script will produce. It deliberately stops short of
launching GPU training (that runs under WSL2 via the emitted script) so the prep
step is safe to run inside the app and fully testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config.models import get_configs

from . import dataset as ds
from . import recipe as rc
from .catalog import ModelEntry, TrainMethod, roles_for_model, trainable_models
from .modelfile import render_modelfile, trained_tag, write_modelfile


@dataclass
class BuildResult:
    model: str
    sft_path: Path
    sft_count: int
    dpo_path: Path | None
    dpo_count: int
    script_path: Path
    modelfile_path: Path
    trained_tag: str
    skipped: str = ""   # non-empty when the model could not be prepared


def _filter_sft_for_model(examples: list[ds.SFTExample], model: str) -> list[ds.SFTExample]:
    roles = roles_for_model(model)
    matched = [ex for ex in examples if str(ex.get("mode")) in roles]
    # A model with no mode-tagged history still benefits from general chat data.
    return matched if matched else examples


def _system_and_temp(model: str) -> tuple[str, float | None]:
    for role, cfg in get_configs().items():
        if cfg.model == model:
            return cfg.system_prompt, cfg.temperature
    return "", None


def prepare_model(
    entry: ModelEntry,
    out_dir: Path,
    *,
    sft_examples: list[ds.SFTExample],
    dpo_pairs: list[ds.DPOPair],
) -> BuildResult:
    """Write datasets, training script and Modelfile for one model."""
    model = entry.model
    safe = model.replace(":", "_").replace("/", "_")
    model_dir = out_dir / safe
    tag = trained_tag(model)

    hf_repo = rc.hf_repo_for(model)
    sft_path = model_dir / "sft.jsonl"
    dpo_path = model_dir / "dpo.jsonl"
    script_path = model_dir / "train.py"
    modelfile_path = model_dir / "Modelfile"

    if entry.method is not TrainMethod.TEXT_LORA or hf_repo is None:
        reason = entry.note or f"No HF base mapping for {model}; cannot emit a text recipe."
        return BuildResult(
            model=model, sft_path=sft_path, sft_count=0, dpo_path=None, dpo_count=0,
            script_path=script_path, modelfile_path=modelfile_path, trained_tag=tag,
            skipped=reason,
        )

    model_sft = _filter_sft_for_model(sft_examples, model)
    sft_count = ds.write_jsonl(sft_path, model_sft)
    dpo_count = ds.write_jsonl(dpo_path, dpo_pairs) if dpo_pairs else 0
    dpo_arg = str(dpo_path) if dpo_count else None

    rc.write_training_script(
        script_path,
        rc.RecipeConfig(
            model=model,
            hf_repo=hf_repo,
            sft_path=str(sft_path),
            dpo_path=dpo_arg,
            output_dir=str(model_dir / "out"),
        ),
    )

    system_prompt, temperature = _system_and_temp(model)
    adapter_gguf = str(model_dir / "out" / "gguf")
    write_modelfile(
        modelfile_path,
        render_modelfile(
            base=model,
            adapter_path=adapter_gguf,
            system_prompt=system_prompt,
            temperature=temperature,
        ),
    )

    return BuildResult(
        model=model, sft_path=sft_path, sft_count=sft_count,
        dpo_path=dpo_path if dpo_count else None, dpo_count=dpo_count,
        script_path=script_path, modelfile_path=modelfile_path, trained_tag=tag,
    )


def prepare_all(out_dir: Path) -> list[BuildResult]:
    """Prepare training artifacts for every text-trainable model in the stack."""
    sft_examples = ds.build_sft_examples() + ds.load_external_sft(out_dir / "sources")
    dpo_pairs = ds.build_dpo_pairs()
    results: list[BuildResult] = []
    for entry in trainable_models(TrainMethod.TEXT_LORA):
        results.append(
            prepare_model(entry, out_dir, sft_examples=sft_examples, dpo_pairs=dpo_pairs)
        )
    return results
