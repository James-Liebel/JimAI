"""Emit a self-contained QLoRA (+optional DPO) training script per model.

Actual weight training needs a CUDA GPU and the Unsloth/TRL toolchain, which
runs under WSL2 on this Windows box — not inside the FastAPI process. So rather
than import torch here, this renders a standalone Python script (and a one-line
requirements hint) that the user runs on the GPU. The script:

  1. loads the base model 4-bit with Unsloth,
  2. attaches a LoRA adapter,
  3. SFT-trains on the chat JSONL, then DPO-trains on the preference JSONL if
     present,
  4. exports a GGUF adapter Unsloth/Ollama can consume.

Placeholders are substituted with ``str.replace`` (not ``.format``) because the
template is real Python full of braces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PIP_REQUIREMENTS = (
    'pip install "unsloth[cu121] @ git+https://github.com/unslothai/unsloth.git" '
    '"trl>=0.9" "peft>=0.11" "datasets>=2.19" "transformers>=4.43"'
)


@dataclass
class RecipeConfig:
    model: str                       # Ollama tag, e.g. "qwen3:8b"
    hf_repo: str                     # HF base repo the GGUF maps to (training source)
    sft_path: str                    # JSONL of {"messages":[...]}
    dpo_path: str | None             # JSONL of {"prompt","chosen","rejected"} or None
    output_dir: str                  # where the adapter/GGUF lands
    max_seq_len: int = 4096
    lora_rank: int = 16
    lora_alpha: int = 16
    learning_rate: float = 2e-4
    epochs: float = 1.0
    batch_size: int = 2
    grad_accum: int = 4
    extra: dict[str, str] = field(default_factory=dict)


# HF repos that the local Ollama Qwen tags are derived from. Used as the
# training base; the trained adapter still loads onto the local GGUF in Ollama.
HF_BASE_REPOS: dict[str, str] = {
    "qwen3:14b": "Qwen/Qwen3-14B",
    "qwen3:8b": "Qwen/Qwen3-8B",
    "qwen2.5-coder:14b": "Qwen/Qwen2.5-Coder-14B-Instruct",
    "qwen2.5-coder:7b": "Qwen/Qwen2.5-Coder-7B-Instruct",
    "qwen2.5-coder:3b": "Qwen/Qwen2.5-Coder-3B-Instruct",
    "qwen2-math:7b-instruct": "Qwen/Qwen2-Math-7B-Instruct",
    "qwen2.5:32b-instruct-q3_k_s": "Qwen/Qwen2.5-32B-Instruct",
}


def hf_repo_for(model: str) -> str | None:
    """Best-effort HF base repo for an Ollama tag (training source weights)."""
    return HF_BASE_REPOS.get(model)


_TEMPLATE = '''"""Auto-generated QLoRA + DPO training script for @@MODEL@@.

Run on a CUDA GPU (WSL2 on Windows). Install deps first:
    @@PIP@@
"""

import json
from pathlib import Path

from datasets import Dataset
from unsloth import FastLanguageModel
from trl import SFTTrainer, SFTConfig

HF_REPO = "@@HF_REPO@@"
SFT_PATH = Path(r"@@SFT_PATH@@")
DPO_PATH = @@DPO_PATH@@
OUTPUT_DIR = Path(r"@@OUTPUT_DIR@@")
MAX_SEQ_LEN = @@MAX_SEQ_LEN@@


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main():
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=HF_REPO,
        max_seq_length=MAX_SEQ_LEN,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=@@LORA_RANK@@,
        lora_alpha=@@LORA_ALPHA@@,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth",
    )

    def to_text(example):
        return {"text": tokenizer.apply_chat_template(
            example["messages"], tokenize=False, add_generation_prompt=False)}

    sft_rows = load_jsonl(SFT_PATH)
    if sft_rows:
        sft_ds = Dataset.from_list(sft_rows).map(to_text)
        SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=sft_ds,
            args=SFTConfig(
                dataset_text_field="text",
                max_seq_length=MAX_SEQ_LEN,
                per_device_train_batch_size=@@BATCH_SIZE@@,
                gradient_accumulation_steps=@@GRAD_ACCUM@@,
                learning_rate=@@LEARNING_RATE@@,
                num_train_epochs=@@EPOCHS@@,
                output_dir=str(OUTPUT_DIR / "sft"),
                logging_steps=10,
            ),
        ).train()

    if DPO_PATH is not None and Path(DPO_PATH).exists():
        from trl import DPOTrainer, DPOConfig
        dpo_rows = load_jsonl(DPO_PATH)
        if dpo_rows:
            dpo_ds = Dataset.from_list(dpo_rows)
            DPOTrainer(
                model=model,
                tokenizer=tokenizer,
                train_dataset=dpo_ds,
                args=DPOConfig(
                    beta=0.1,
                    per_device_train_batch_size=1,
                    gradient_accumulation_steps=@@GRAD_ACCUM@@,
                    learning_rate=5e-6,
                    num_train_epochs=1,
                    output_dir=str(OUTPUT_DIR / "dpo"),
                    logging_steps=10,
                ),
            ).train()

    # GGUF adapter Ollama can ADAPTER-load (see training/modelfile.py).
    model.save_pretrained_gguf(str(OUTPUT_DIR / "gguf"), tokenizer)
    print("Saved adapter to", OUTPUT_DIR / "gguf")


if __name__ == "__main__":
    main()
'''


def render_training_script(cfg: RecipeConfig) -> str:
    """Render the runnable training script for one model."""
    dpo_literal = f'Path(r"{cfg.dpo_path}")' if cfg.dpo_path else "None"
    replacements = {
        "@@MODEL@@": cfg.model,
        "@@PIP@@": PIP_REQUIREMENTS,
        "@@HF_REPO@@": cfg.hf_repo,
        "@@SFT_PATH@@": cfg.sft_path,
        "@@DPO_PATH@@": dpo_literal,
        "@@OUTPUT_DIR@@": cfg.output_dir,
        "@@MAX_SEQ_LEN@@": str(cfg.max_seq_len),
        "@@LORA_RANK@@": str(cfg.lora_rank),
        "@@LORA_ALPHA@@": str(cfg.lora_alpha),
        "@@LEARNING_RATE@@": repr(cfg.learning_rate),
        "@@EPOCHS@@": repr(cfg.epochs),
        "@@BATCH_SIZE@@": str(cfg.batch_size),
        "@@GRAD_ACCUM@@": str(cfg.grad_accum),
    }
    script = _TEMPLATE
    for token, value in replacements.items():
        script = script.replace(token, value)
    return script


def write_training_script(path: Path, cfg: RecipeConfig) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_training_script(cfg), encoding="utf-8")
    return path
