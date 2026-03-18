"""LoRA fine-tuning script using Unsloth + TRL for style adaptation."""

import sys
from pathlib import Path


def main():
    try:
        from unsloth import FastLanguageModel
        from trl import SFTTrainer
        from transformers import TrainingArguments
        from datasets import load_dataset
    except ImportError:
        print("Missing dependencies. Install with:")
        print("  pip install unsloth transformers trl datasets peft torch")
        sys.exit(1)

    corpus_path = Path("data/corpus/training.jsonl")
    output_dir = Path("data/finetune/style-model")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not corpus_path.exists():
        print(f"Training data not found at {corpus_path}")
        print("Run 'python scripts/build_corpus.py <directory>' first")
        sys.exit(1)

    print("Loading base model (4-bit quantized)...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name="unsloth/mistral-7b-instruct-v0.3-bnb-4bit",
        max_seq_length=4096,
        load_in_4bit=True,
    )

    print("Applying LoRA adapter...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_alpha=32,
        lora_dropout=0.05,
    )

    print("Loading training data...")
    dataset = load_dataset("json", data_files=str(corpus_path), split="train")

    def format_prompt(example):
        return f"### Instruction:\n{example['prompt']}\n\n### Response:\n{example['completion']}"

    print(f"Training on {len(dataset)} examples...")

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=3,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        warmup_steps=50,
        logging_steps=50,
        save_steps=200,
        fp16=True,
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=training_args,
        formatting_func=format_prompt,
        max_seq_length=4096,
    )

    print("Starting training...")
    trainer.train()

    print(f"Saving model to {output_dir}...")
    model.save_pretrained_merged(str(output_dir), tokenizer)

    print("Fine-tuning complete!")
    print(f"Model saved to: {output_dir}")


if __name__ == "__main__":
    main()
