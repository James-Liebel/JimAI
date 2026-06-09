"""External instruction datasets to make each role's model stronger.

The canonical source of fine-tuning data is curated instruction datasets on the
HuggingFace Hub — not scraped web pages. This maps each JimAI role to a vetted,
permissively-licensed dataset and converts it into the same
``{"messages": [...]}`` SFT format the local data uses, so external and
self-generated data train through one path.

``fetch_sft`` streams (no full download) and takes ``limit`` rows, attaching the
role's system prompt so the model trains the way it will be served.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class DataSource:
    role: str
    hf_id: str
    converter: str               # key into _CONVERTERS
    config: str | None = None
    split: str = "train"
    license: str = ""


# Role → dataset. Licenses noted; all are usable for a local personal workspace.
SOURCES: dict[str, DataSource] = {
    "code": DataSource("code", "sahil2801/CodeAlpaca-20k", "alpaca", license="CC-BY-4.0"),
    "data": DataSource("data", "sahil2801/CodeAlpaca-20k", "alpaca", license="CC-BY-4.0"),
    "math": DataSource("math", "openai/gsm8k", "gsm8k", config="main", license="MIT"),
    "finance": DataSource("finance", "gbharti/finance-alpaca", "alpaca", license="Apache-2.0"),
    "chat": DataSource("chat", "databricks/databricks-dolly-15k", "dolly", license="CC-BY-SA-3.0"),
    "writing": DataSource("writing", "databricks/databricks-dolly-15k", "dolly", license="CC-BY-SA-3.0"),
}


def _alpaca(row: dict[str, Any]) -> tuple[str, str]:
    instruction = str(row.get("instruction") or "").strip()
    extra = str(row.get("input") or "").strip()
    user = f"{instruction}\n\n{extra}" if extra else instruction
    return user, str(row.get("output") or "").strip()


def _dolly(row: dict[str, Any]) -> tuple[str, str]:
    instruction = str(row.get("instruction") or "").strip()
    context = str(row.get("context") or "").strip()
    user = f"{instruction}\n\n{context}" if context else instruction
    return user, str(row.get("response") or "").strip()


def _gsm8k(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("question") or "").strip(), str(row.get("answer") or "").strip()


_CONVERTERS: dict[str, Callable[[dict[str, Any]], tuple[str, str]]] = {
    "alpaca": _alpaca,
    "dolly": _dolly,
    "gsm8k": _gsm8k,
}


def fetch_sft(role: str, limit: int = 2000) -> list[dict[str, Any]]:
    """Stream up to ``limit`` SFT examples for a role from its HF dataset."""
    from datasets import load_dataset

    from config.models import get_configs

    source = SOURCES.get(role)
    if source is None:
        raise ValueError(f"No external data source registered for role '{role}'.")
    convert = _CONVERTERS[source.converter]

    cfg = get_configs().get(role) or get_configs()["chat"]
    system_prompt = cfg.system_prompt

    stream = load_dataset(
        source.hf_id, source.config, split=source.split, streaming=True
    ) if source.config else load_dataset(source.hf_id, split=source.split, streaming=True)

    examples: list[dict[str, Any]] = []
    for row in stream:
        user, assistant = convert(row)
        if not user or not assistant:
            continue
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user})
        messages.append({"role": "assistant", "content": assistant})
        examples.append({"messages": messages, "mode": role})
        if len(examples) >= limit:
            break
    return examples
