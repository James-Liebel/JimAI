"""
Per-domain, per-mode inference parameters.
Context window size directly affects VRAM — scale with caution.
"""
from config.models import SpeedMode

INFERENCE_PARAMS: dict[tuple[str, SpeedMode], dict] = {
    # Math: low temp, medium ctx — proofs don't need 32k tokens
    ("math", SpeedMode.FAST): {"temperature": 0.05, "num_ctx": 8192, "repeat_penalty": 1.05},
    ("math", SpeedMode.BALANCED): {"temperature": 0.1, "num_ctx": 16384, "repeat_penalty": 1.05},
    ("math", SpeedMode.DEEP): {"temperature": 0.1, "num_ctx": 32768, "repeat_penalty": 1.05},

    # Code: very low temp, large ctx for full repo understanding
    ("code", SpeedMode.FAST): {"temperature": 0.05, "num_ctx": 8192, "repeat_penalty": 1.1},
    ("code", SpeedMode.BALANCED): {"temperature": 0.05, "num_ctx": 32768, "repeat_penalty": 1.1},
    ("code", SpeedMode.DEEP): {"temperature": 0.05, "num_ctx": 65536, "repeat_penalty": 1.1},

    # Chat: higher temp, moderate ctx
    ("chat", SpeedMode.FAST): {"temperature": 0.7, "num_ctx": 4096, "repeat_penalty": 1.15},
    ("chat", SpeedMode.BALANCED): {"temperature": 0.7, "num_ctx": 8192, "repeat_penalty": 1.15},
    ("chat", SpeedMode.DEEP): {"temperature": 0.6, "num_ctx": 16384, "repeat_penalty": 1.15},

    # Finance: low temp, large ctx for 10-Ks and long filings
    ("finance", SpeedMode.FAST): {"temperature": 0.1, "num_ctx": 8192, "repeat_penalty": 1.05},
    ("finance", SpeedMode.BALANCED): {"temperature": 0.1, "num_ctx": 32768, "repeat_penalty": 1.05},
    ("finance", SpeedMode.DEEP): {"temperature": 0.1, "num_ctx": 65536, "repeat_penalty": 1.05},

    # Vision: moderate temp, ctx is less relevant (images use VRAM not tokens)
    ("vision", SpeedMode.FAST): {"temperature": 0.2, "num_ctx": 4096, "repeat_penalty": 1.1},
    ("vision", SpeedMode.BALANCED): {"temperature": 0.2, "num_ctx": 8192, "repeat_penalty": 1.1},
    ("vision", SpeedMode.DEEP): {"temperature": 0.2, "num_ctx": 8192, "repeat_penalty": 1.1},

    # Data science: low temp, large ctx for datasets and notebooks
    ("data", SpeedMode.FAST): {"temperature": 0.1, "num_ctx": 8192, "repeat_penalty": 1.1},
    ("data", SpeedMode.BALANCED): {"temperature": 0.1, "num_ctx": 32768, "repeat_penalty": 1.1},
    ("data", SpeedMode.DEEP): {"temperature": 0.1, "num_ctx": 65536, "repeat_penalty": 1.1},

    # Writing: same as chat
    ("writing", SpeedMode.FAST): {"temperature": 0.75, "num_ctx": 4096, "repeat_penalty": 1.15},
    ("writing", SpeedMode.BALANCED): {"temperature": 0.75, "num_ctx": 8192, "repeat_penalty": 1.15},
    ("writing", SpeedMode.DEEP): {"temperature": 0.75, "num_ctx": 16384, "repeat_penalty": 1.15},

    # Completion: hardcoded fast — latency is everything
    ("completion", SpeedMode.FAST): {"temperature": 0.05, "num_ctx": 2048, "repeat_penalty": 1.0},
    ("completion", SpeedMode.BALANCED): {"temperature": 0.05, "num_ctx": 2048, "repeat_penalty": 1.0},
    ("completion", SpeedMode.DEEP): {"temperature": 0.05, "num_ctx": 2048, "repeat_penalty": 1.0},
}


def get_inference_params(domain: str, speed_mode: SpeedMode) -> dict:
    return INFERENCE_PARAMS.get(
        (domain, speed_mode),
        {"temperature": 0.5, "num_ctx": 8192, "repeat_penalty": 1.1},
    )
