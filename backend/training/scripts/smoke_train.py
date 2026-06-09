"""Windows-native LoRA smoke test — proves the GPU training path works.

Unlike the Unsloth recipe (Linux/WSL2), this uses plain HF PEFT + TRL with a
bf16 LoRA (no bitsandbytes/4-bit), which is the reliable path on native Windows
with a Blackwell GPU. It trains a small LoRA on the generated SFT JSONL and saves
the adapter. It is a *capability proof*, not a quality run — the dataset is tiny.

    python -m training.scripts.smoke_train --hf Qwen/Qwen2.5-Coder-3B-Instruct \
        --sft ../data/training/qwen2.5-coder_3b/sft.jsonl \
        --out ../data/training/qwen2.5-coder_3b/out --max-steps 20
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="LoRA smoke test on the local GPU.")
    parser.add_argument("--hf", required=True, help="HF base repo")
    parser.add_argument("--sft", required=True, help="SFT JSONL ({'messages':[...]})")
    parser.add_argument("--out", required=True, help="adapter output dir")
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--max-seq-len", type=int, default=1024)
    args = parser.parse_args()

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    if not torch.cuda.is_available():
        print("CUDA not available — aborting smoke test.")
        return 1
    print(f"GPU: {torch.cuda.get_device_name(0)} | torch {torch.__version__}")

    tokenizer = AutoTokenizer.from_pretrained(args.hf)
    model = AutoModelForCausalLM.from_pretrained(
        args.hf, dtype=torch.bfloat16, device_map="cuda",
    )

    rows = load_jsonl(Path(args.sft))
    print(f"SFT examples: {len(rows)}")

    def to_text(example: dict) -> dict:
        return {"text": tokenizer.apply_chat_template(
            example["messages"], tokenize=False, add_generation_prompt=False)}

    dataset = Dataset.from_list(rows).map(to_text, remove_columns=["messages", "mode"])

    lora = LoraConfig(
        r=8, lora_alpha=16, lora_dropout=0.0, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        peft_config=lora,
        processing_class=tokenizer,
        args=SFTConfig(
            dataset_text_field="text",
            max_length=args.max_seq_len,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=1,
            learning_rate=2e-4,
            max_steps=args.max_steps,
            logging_steps=1,
            output_dir=str(Path(args.out) / "sft"),
            report_to=[],
        ),
    )
    result = trainer.train()
    trainer.save_model(str(Path(args.out) / "adapter"))
    print(f"train_loss={result.training_loss:.4f}")
    print(f"adapter saved to {Path(args.out) / 'adapter'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
