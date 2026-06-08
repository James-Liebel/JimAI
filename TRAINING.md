# Training JimAI's models to be stronger (local LoRA / DPO)

JimAI ships strong base models, but you can fine-tune them on **your own usage**
so they get better at *your* tasks — without leaving the Ollama-only stack. The
`backend/training/` subsystem turns chat history and the self-improve pipeline's
accept/reject verdicts into training data, emits a QLoRA + DPO script per model,
and loads the trained adapter back into Ollama.

> Weight training needs a CUDA GPU. On this Windows box that means **WSL2 + an
> NVIDIA GPU**. The app only *prepares* artifacts; you run the training script in
> WSL. Nothing here touches the cloud.

## The loop

```
chat history + review verdicts          (mine your own data)
        │   backend/training/dataset.py
        ▼
   SFT + DPO JSONL  ──►  train.py (QLoRA + DPO, Unsloth/TRL)   (train on GPU/WSL2)
        │                       │  backend/training/recipe.py
        │                       ▼
        │                 GGUF adapter
        ▼                       │
   Modelfile  ◄──────────────────┘   (reload into Ollama)
        │   backend/training/modelfile.py → `ollama create`
        ▼
   jimai-qwen3:8b  (drop-in stronger model)
```

## 1. Prepare artifacts (safe, runs anywhere)

```bash
# from backend/
python -m training.run list          # every model + how it can be trained
python -m training.run build-all     # datasets + train.py + Modelfile for all models
python -m training.run build --model qwen3:8b   # just one
```

Output lands in `data/training/<model>/`:
`sft.jsonl`, `dpo.jsonl` (when preference pairs exist), `train.py`, `Modelfile`.

Embedding (`nomic-embed-text`) and vision (`qwen2.5vl:7b`) models are listed but
**excluded** from the text recipe — they need different objectives; `list` prints
why.

## 2. Train on a GPU (WSL2)

```bash
pip install "unsloth[cu121] @ git+https://github.com/unslothai/unsloth.git" \
            "trl>=0.9" "peft>=0.11" "datasets>=2.19" "transformers>=4.43"
python data/training/qwen3_8b/train.py
```

A 7–8B QLoRA fits in ~12–16 GB VRAM. The script SFT-trains on the chat data,
then DPO-trains on preference pairs if present, and writes a GGUF adapter.

## 3. Reload into Ollama

```bash
python -m training.run create --tag jimai-qwen3:8b \
       --modelfile data/training/qwen3_8b/Modelfile
ollama run jimai-qwen3:8b
```

The trained variant is prefixed `jimai-` so it never shadows the stock model.
Point a role at it by adding the tag to `backend/config/models.py`.

## Growing the dataset

- **SFT** comes from every chat you have — it grows as you use the app.
- **DPO** comes from the self-improve pipeline: when a proposed change is
  **approved** and another for the same run is **rejected**, that becomes a
  chosen/rejected pair (`training/dataset.py:reviews_to_dpo`). Early on this is
  often 0 — use the review gate (approve/reject diffs) to accumulate signal.

## Caveats (read before trusting a trained model)

- Fine-tuning a small model rarely makes it *generally smarter*; it adapts
  **style, domain, and format**. It can regress on general ability
  (catastrophic forgetting) — always keep a held-out eval and compare against
  the stock model before promoting a `jimai-` variant.
- More data + clean data beats more epochs. A few dozen examples is a smoke
  test, not a real run.
