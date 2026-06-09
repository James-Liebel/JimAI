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

**External data (optional).** To go beyond your own history, pull a curated
instruction set for a role — `build*` folds anything under
`data/training/sources/*.jsonl` in alongside your mined data:

```bash
python -m training.run fetch --role code   # → data/training/sources/code.jsonl
```

## 2. Train on a GPU

### Native Windows (no WSL) — verified on an RTX 5080 Laptop

The reliable path on this box. Plain HF PEFT + TRL with a **bf16 LoRA** (no
bitsandbytes/4-bit, which is flaky on native Windows + Blackwell):

```powershell
# Blackwell (RTX 50xx, sm_120) needs the cu128 wheels, NOT cu121:
pip install --upgrade torch --index-url https://download.pytorch.org/whl/cu128
pip install "transformers>=5.0" "trl>=1.5" "peft>=0.18" "datasets>=3.0" "accelerate>=1.0"

# TRL reads a UTF-8 template with the locale codec — on Windows force UTF-8 mode:
$env:PYTHONUTF8 = "1"
python -m training.smoke_train --hf Qwen/Qwen2.5-Coder-3B-Instruct `
    --sft ../data/training/qwen2.5-coder_3b/sft.jsonl `
    --out ../data/training/qwen2.5-coder_3b/out --max-steps 20
```

`smoke_train.py` is a capability proof on a tiny dataset. A 3B bf16 LoRA fits
well under 16 GB; 7–8B in bf16 is tight — drop to the WSL2/4-bit path for those.

### WSL2 + Unsloth (bigger models, 4-bit QLoRA)

```bash
pip install "unsloth[cu128] @ git+https://github.com/unslothai/unsloth.git" \
            "trl>=0.9" "peft>=0.11" "datasets>=2.19" "transformers>=4.43"
python data/training/qwen3_8b/train.py   # the recipe.py-generated script
```

A 7–8B 4-bit QLoRA fits in ~12–16 GB VRAM. The script SFT-trains on the chat
data, then DPO-trains on preference pairs if present, and writes a GGUF adapter.

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
- **External sources** (optional): `training.run fetch --role <role>` streams a
  vetted HuggingFace instruction set (`training/sources.py`) into
  `data/training/sources/`, tagged with the role's system prompt so it trains the
  way it's served. Useful to bootstrap a role before you have much history.
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
