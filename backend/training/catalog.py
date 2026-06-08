"""Enumerate every model in the stack and classify how each can be trained.

The four speed-tier config dicts in ``config.models`` are the source of truth
for which models JimAI runs. This module flattens them into a deduplicated set
of models, records which roles each serves, and decides the training method —
because a causal-LM LoRA recipe is wrong for an embedding or vision model.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from config.models import (
    BALANCED_CONFIGS,
    DEEP_CONFIGS,
    FAST_CONFIGS,
    TURBO_CONFIGS,
    ModelConfig,
)

_ALL_CONFIGS: tuple[dict[str, ModelConfig], ...] = (
    BALANCED_CONFIGS,
    FAST_CONFIGS,
    DEEP_CONFIGS,
    TURBO_CONFIGS,
)


class TrainMethod(str, Enum):
    """How a given model can be fine-tuned locally."""

    TEXT_LORA = "text_lora"      # causal-LM QLoRA / DPO — the default, supported path
    VISION_LORA = "vision_lora"  # multimodal: needs image+text pairs and a VL trainer
    EMBEDDING = "embedding"      # contrastive objective, not next-token — different toolchain
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class ModelEntry:
    model: str                  # exact Ollama tag, e.g. "qwen3:8b"
    roles: tuple[str, ...]      # roles this model serves across all tiers, sorted
    method: TrainMethod
    note: str = ""              # why a non-default method was chosen


def _classify(model: str) -> tuple[TrainMethod, str]:
    base = model.lower().split(":", 1)[0]
    if "embed" in base or "nomic" in base:
        return (
            TrainMethod.EMBEDDING,
            "Embedding model: fine-tune with a contrastive objective, not causal LM. "
            "Out of scope for the QLoRA/DPO recipe.",
        )
    if base.endswith("vl") or "vision" in base:
        return (
            TrainMethod.VISION_LORA,
            "Vision-language model: needs image+text pairs and a multimodal trainer "
            "(Unsloth supports it, but the text recipe does not).",
        )
    return TrainMethod.TEXT_LORA, ""


def all_models() -> list[ModelEntry]:
    """Every distinct model across all speed tiers, with its roles and method."""
    roles_by_model: dict[str, set[str]] = {}
    for configs in _ALL_CONFIGS:
        for role, cfg in configs.items():
            roles_by_model.setdefault(cfg.model, set()).add(role)

    entries: list[ModelEntry] = []
    for model in sorted(roles_by_model):
        method, note = _classify(model)
        entries.append(
            ModelEntry(
                model=model,
                roles=tuple(sorted(roles_by_model[model])),
                method=method,
                note=note,
            )
        )
    return entries


def trainable_models(method: TrainMethod = TrainMethod.TEXT_LORA) -> list[ModelEntry]:
    """Models trainable with the given method (default: the supported text LoRA path)."""
    return [entry for entry in all_models() if entry.method == method]


def roles_for_model(model: str) -> set[str]:
    """The set of roles (chat, code, math, …) served by a model across all tiers."""
    roles: set[str] = set()
    for configs in _ALL_CONFIGS:
        for role, cfg in configs.items():
            if cfg.model == model:
                roles.add(role)
    return roles
