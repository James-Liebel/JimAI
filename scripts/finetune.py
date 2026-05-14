"""LoRA fine-tuning for JimAI's chat persona — Qwen2.5 base, real chat history.

Why Qwen, not Mistral
---------------------
The runtime serves Qwen2.5-* models (see backend/config/models.py). Training
a Mistral adapter and trying to use it at inference time would force a model
swap and lose the routing/inference-param tuning the rest of the app relies
on. Keeping the base aligned with the runtime means the adapter slots
straight into the existing Ollama setup via a Modelfile FROM directive.

Inputs
------
A JSONL training file produced by scripts/build_corpus.py (or any compatible
producer). Each line: {"prompt": "...", "completion": "..."}.

Outputs
-------
A merged LoRA adapter under data/finetune/<run-id>/ plus a Modelfile snippet
that can be imported with `ollama create jimai-tuned -f Modelfile`.

Held-out eval
-------------
The script keeps the last --eval-frac fraction (default 0.05) as a held-out
test split and reports loss before/after, so a regression on the validation
set is visible. This is not a substitute for end-to-end behavioural eval, but
it catches catastrophic forgetting on the training distribution.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


DEFAULT_BASE = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit"
DEFAULT_TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LoRA fine-tune a Qwen base on JimAI's chat corpus.")
    p.add_argument("--corpus", default="data/corpus/training.jsonl",
                   help="Training data JSONL (prompt/completion pairs).")
    p.add_argument("--base", default=DEFAULT_BASE,
                   help=f"Base model to load (default: {DEFAULT_BASE}).")
    p.add_argument("--out", default=None,
                   help="Output directory. Default: data/finetune/<timestamp>/.")
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--grad-accum", type=int, default=4)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--max-seq-length", type=int, default=4096)
    p.add_argument("--r", type=int, default=16, help="LoRA rank.")
    p.add_argument("--alpha", type=int, default=32, help="LoRA alpha.")
    p.add_argument("--dropout", type=float, default=0.05)
    p.add_argument("--eval-frac", type=float, default=0.05,
                   help="Fraction of corpus held out for eval (last N rows).")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def main() -> None:
    args = parse_args()

    try:
        from unsloth import FastLanguageModel
        from trl import SFTTrainer
        from transformers import TrainingArguments
        from datasets import load_dataset
    except ImportError:
        print("Missing dependencies. Install with:")
        print("  pip install unsloth transformers trl datasets peft torch")
        sys.exit(1)

    corpus_path = Path(args.corpus)
    if not corpus_path.exists():
        print(f"Training data not found at {corpus_path}")
        print("Build it first with: python scripts/build_corpus.py <directory>")
        sys.exit(1)

    run_id = time.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.out) if args.out else Path("data/finetune") / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/5] Loading base model: {args.base}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base,
        max_seq_length=args.max_seq_length,
        load_in_4bit=True,
    )

    print(f"[2/5] Applying LoRA (r={args.r}, alpha={args.alpha}, dropout={args.dropout})")
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.r,
        target_modules=DEFAULT_TARGET_MODULES,
        lora_alpha=args.alpha,
        lora_dropout=args.dropout,
        random_state=args.seed,
    )

    print(f"[3/5] Loading and splitting corpus from {corpus_path}")
    full = load_dataset("json", data_files=str(corpus_path), split="train")
    n = len(full)
    eval_n = max(1, int(n * max(0.0, min(args.eval_frac, 0.5))))
    train_ds = full.select(range(n - eval_n)) if eval_n > 0 else full
    eval_ds = full.select(range(n - eval_n, n)) if eval_n > 0 else None
    print(f"      train={len(train_ds)}  eval={0 if eval_ds is None else len(eval_ds)}")

    def format_prompt(example):
        # Qwen2.5-Instruct expects ChatML — but Unsloth's SFTTrainer accepts
        # plain instruction/response with `formatting_func`. Keep it close to
        # how the runtime feeds messages so adapter behaviour transfers.
        return (
            f"<|im_start|>user\n{example['prompt']}<|im_end|>\n"
            f"<|im_start|>assistant\n{example['completion']}<|im_end|>"
        )

    print(f"[4/5] Training for {args.epochs} epochs (batch={args.batch_size} × grad_accum={args.grad_accum})")
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        warmup_steps=50,
        logging_steps=25,
        save_steps=200,
        eval_steps=200 if eval_ds is not None else None,
        eval_strategy="steps" if eval_ds is not None else "no",
        fp16=True,
        seed=args.seed,
        report_to="none",
    )
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        args=training_args,
        formatting_func=format_prompt,
        max_seq_length=args.max_seq_length,
    )

    if eval_ds is not None:
        pre = trainer.evaluate()
        print(f"      eval_loss BEFORE training: {pre.get('eval_loss'):.4f}")

    trainer.train()

    if eval_ds is not None:
        post = trainer.evaluate()
        print(f"      eval_loss AFTER training:  {post.get('eval_loss'):.4f}")

    print(f"[5/5] Saving merged model + Modelfile to {output_dir}")
    model.save_pretrained_merged(str(output_dir), tokenizer)

    # Emit a Modelfile so the user can `ollama create jimai-tuned -f Modelfile`.
    modelfile = output_dir / "Modelfile"
    modelfile.write_text(
        f"# Generated by scripts/finetune.py — base: {args.base}\n"
        f"FROM {output_dir.resolve()}\n"
        "PARAMETER temperature 0.5\n"
        "PARAMETER num_ctx 16384\n"
        "PARAMETER stop \"<|im_end|>\"\n"
        "PARAMETER stop \"<|im_start|>\"\n",
        encoding="utf-8",
    )

    print()
    print(f"Done. Run:  ollama create jimai-tuned-{run_id} -f {modelfile}")
    print(f"Then set MODEL_ROUTES['chat'].model = 'jimai-tuned-{run_id}' to route chat through your adapter.")


if __name__ == "__main__":
    main()
