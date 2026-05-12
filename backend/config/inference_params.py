"""
Per-domain, per-mode inference parameters.
Context window size directly affects VRAM — scale with caution.
num_batch: controls prefill parallelism — higher = faster TTFT on modern GPUs.
  TURBO: 2048 (3B model, max GPU util), FAST: 2048 (was 512), BALANCED: 2048 (was 1024)

Sampling — qwen3 non-thinking recommendation: top_p=0.8, top_k=20, min_p=0.
Applied to BALANCED math/code/chat/writing/data/finance tiers below; this trims
the long tail and visibly cuts hallucinated tokens vs. the ollama default
(top_p=0.9, top_k=40) without slowing inference.
"""
from config.models import SpeedMode

# qwen3-recommended sampling for non-thinking mode. Spreading it as a base dict
# lets us merge per-row without repeating three keys 12 times.
_QWEN3_NONTHINK = {"top_p": 0.8, "top_k": 20, "min_p": 0.0}

INFERENCE_PARAMS: dict[tuple[str, SpeedMode], dict] = {
    # ── TURBO: 3B-8B, minimal ctx, instant TTFT ──────────────────────────────
    ("math", SpeedMode.TURBO): {"temperature": 0.1, "num_ctx": 4096, "num_predict": 768, "num_batch": 2048, "repeat_penalty": 1.05, "think": False},
    ("code", SpeedMode.TURBO): {"temperature": 0.05, "num_ctx": 4096, "num_predict": 1024, "num_batch": 2048, "repeat_penalty": 1.1, "think": False},
    ("chat", SpeedMode.TURBO): {"temperature": 0.7, "num_ctx": 2048, "num_predict": 384, "num_batch": 2048, "repeat_penalty": 1.15, "think": False},
    ("finance", SpeedMode.TURBO): {"temperature": 0.1, "num_ctx": 4096, "num_predict": 768, "num_batch": 2048, "repeat_penalty": 1.05, "think": False},
    ("vision", SpeedMode.TURBO): {"temperature": 0.2, "num_ctx": 4096, "num_predict": 512, "num_batch": 2048, "repeat_penalty": 1.1},
    ("data", SpeedMode.TURBO): {"temperature": 0.1, "num_ctx": 4096, "num_predict": 1024, "num_batch": 2048, "repeat_penalty": 1.1, "think": False},
    ("writing", SpeedMode.TURBO): {"temperature": 0.75, "num_ctx": 2048, "num_predict": 512, "num_batch": 2048, "repeat_penalty": 1.15, "think": False},
    ("completion", SpeedMode.TURBO): {"temperature": 0.05, "num_ctx": 1024, "num_predict": 96, "num_batch": 2048, "repeat_penalty": 1.0, "think": False},

    # ── FAST: 7-8B, bumped num_batch 512→2048 for GPU prefill parallelism ────
    ("math", SpeedMode.FAST): {"temperature": 0.05, "num_ctx": 8192, "num_predict": 1024, "num_batch": 2048, "repeat_penalty": 1.05, "think": False},
    ("math", SpeedMode.BALANCED): {"temperature": 0.1, "num_ctx": 16384, "num_predict": 2048, "num_batch": 1024, "repeat_penalty": 1.05, "think": False, **_QWEN3_NONTHINK},
    ("math", SpeedMode.DEEP): {"temperature": 0.1, "num_ctx": 32768, "num_predict": 4096, "num_batch": 1024, "repeat_penalty": 1.05},

    ("code", SpeedMode.FAST): {"temperature": 0.05, "num_ctx": 8192, "num_predict": 1536, "num_batch": 2048, "repeat_penalty": 1.1, "think": False},
    ("code", SpeedMode.BALANCED): {"temperature": 0.05, "num_ctx": 16384, "num_predict": 3072, "num_batch": 1024, "repeat_penalty": 1.1, "think": False, **_QWEN3_NONTHINK},
    ("code", SpeedMode.DEEP): {"temperature": 0.05, "num_ctx": 65536, "num_predict": 6144, "num_batch": 1024, "repeat_penalty": 1.1},

    ("chat", SpeedMode.FAST): {"temperature": 0.7, "num_ctx": 4096, "num_predict": 512, "num_batch": 2048, "repeat_penalty": 1.15, "think": False},
    ("chat", SpeedMode.BALANCED): {"temperature": 0.7, "num_ctx": 8192, "num_predict": 1024, "num_batch": 1024, "repeat_penalty": 1.15, "think": False, **_QWEN3_NONTHINK},
    ("chat", SpeedMode.DEEP): {"temperature": 0.6, "num_ctx": 16384, "num_predict": 2048, "num_batch": 1024, "repeat_penalty": 1.15},

    ("finance", SpeedMode.FAST): {"temperature": 0.1, "num_ctx": 8192, "num_predict": 1024, "num_batch": 2048, "repeat_penalty": 1.05, "think": False},
    ("finance", SpeedMode.BALANCED): {"temperature": 0.1, "num_ctx": 16384, "num_predict": 2048, "num_batch": 1024, "repeat_penalty": 1.05, "think": False, **_QWEN3_NONTHINK},
    ("finance", SpeedMode.DEEP): {"temperature": 0.1, "num_ctx": 65536, "num_predict": 4096, "num_batch": 1024, "repeat_penalty": 1.05},

    # Vision: image-bound VRAM — moderate batch across all modes
    ("vision", SpeedMode.FAST): {"temperature": 0.2, "num_ctx": 4096, "num_predict": 512, "num_batch": 512, "repeat_penalty": 1.1},
    ("vision", SpeedMode.BALANCED): {"temperature": 0.2, "num_ctx": 8192, "num_predict": 1024, "num_batch": 512, "repeat_penalty": 1.1},
    ("vision", SpeedMode.DEEP): {"temperature": 0.2, "num_ctx": 8192, "num_predict": 1024, "num_batch": 512, "repeat_penalty": 1.1},

    ("data", SpeedMode.FAST): {"temperature": 0.1, "num_ctx": 8192, "num_predict": 1536, "num_batch": 2048, "repeat_penalty": 1.1, "think": False},
    ("data", SpeedMode.BALANCED): {"temperature": 0.1, "num_ctx": 16384, "num_predict": 3072, "num_batch": 1024, "repeat_penalty": 1.1, "think": False, **_QWEN3_NONTHINK},
    ("data", SpeedMode.DEEP): {"temperature": 0.1, "num_ctx": 65536, "num_predict": 6144, "num_batch": 1024, "repeat_penalty": 1.1},

    ("writing", SpeedMode.FAST): {"temperature": 0.75, "num_ctx": 4096, "num_predict": 768, "num_batch": 2048, "repeat_penalty": 1.15, "think": False},
    ("writing", SpeedMode.BALANCED): {"temperature": 0.75, "num_ctx": 8192, "num_predict": 1536, "num_batch": 1024, "repeat_penalty": 1.15, "think": False, **_QWEN3_NONTHINK},
    ("writing", SpeedMode.DEEP): {"temperature": 0.75, "num_ctx": 16384, "num_predict": 3072, "num_batch": 1024, "repeat_penalty": 1.15},

    ("completion", SpeedMode.FAST): {"temperature": 0.05, "num_ctx": 2048, "num_predict": 128, "num_batch": 2048, "repeat_penalty": 1.0, "think": False},
    ("completion", SpeedMode.BALANCED): {"temperature": 0.05, "num_ctx": 2048, "num_predict": 128, "num_batch": 1024, "repeat_penalty": 1.0, "think": False},
    ("completion", SpeedMode.DEEP): {"temperature": 0.05, "num_ctx": 2048, "num_predict": 256, "num_batch": 1024, "repeat_penalty": 1.0},
}


def get_inference_params(domain: str, speed_mode: SpeedMode) -> dict:
    return INFERENCE_PARAMS.get(
        (domain, speed_mode),
        {"temperature": 0.5, "num_ctx": 8192, "repeat_penalty": 1.1},
    )
