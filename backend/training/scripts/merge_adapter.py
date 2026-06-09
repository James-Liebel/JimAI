"""Merge a trained LoRA adapter into the base weights for Ollama import.

The native-Windows path (``smoke_train.py``) saves a PEFT LoRA adapter, but
Ollama cannot ingest a PEFT adapter directory directly. Merging the adapter into
the base produces a full Qwen2 Safetensors model, which Ollama *does* import
(converting to GGUF itself) — so this closes the train→Ollama loop without
llama.cpp. The merged model lands next to a ``Modelfile`` for ``ollama create``.

    python -m training.scripts.merge_adapter --hf Qwen/Qwen2.5-Coder-3B-Instruct \
        --adapter ../data/training/qwen2.5-coder_3b/out/adapter \
        --out ../data/training/qwen2.5-coder_3b/out/merged
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge a LoRA adapter into base weights.")
    parser.add_argument("--hf", required=True, help="HF base repo the adapter trained on")
    parser.add_argument("--adapter", required=True, help="PEFT adapter dir from training")
    parser.add_argument("--out", required=True, help="output dir for the merged model")
    args = parser.parse_args()

    import torch
    from peft import PeftModel
    from safetensors.torch import save_file
    from transformers import AutoModelForCausalLM, AutoTokenizer

    out_dir = Path(args.out)
    tokenizer = AutoTokenizer.from_pretrained(args.hf)
    # f16, not bf16: Ollama's safetensors→GGUF importer corrupts bf16 weights
    # (produces garbage tokens). Qwen2.5 weights fit f16 range with more mantissa.
    base = AutoModelForCausalLM.from_pretrained(args.hf, dtype=torch.float16)
    merged = PeftModel.from_pretrained(base, args.adapter).merge_and_unload()

    # Qwen2.5-3B ties lm_head to the input embeddings, so transformers drops
    # lm_head.weight on save — and Ollama's GGUF converter doesn't re-tie it,
    # emitting garbage tokens. Write the state dict ourselves with an explicit,
    # cloned (storage-independent) lm_head so the export is self-contained.
    state = merged.state_dict()
    state["lm_head.weight"] = state["model.embed_tokens.weight"].clone()
    state = {key: value.contiguous() for key, value in state.items()}

    out_dir.mkdir(parents=True, exist_ok=True)
    merged.config.tie_word_embeddings = False
    merged.config.save_pretrained(str(out_dir))
    merged.generation_config.save_pretrained(str(out_dir))
    save_file(state, str(out_dir / "model.safetensors"), metadata={"format": "pt"})
    tokenizer.save_pretrained(str(out_dir))
    print(f"merged model saved to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
