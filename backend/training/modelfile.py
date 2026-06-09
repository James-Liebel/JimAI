"""Generate an Ollama Modelfile that loads a trained adapter back into the stack.

After the QLoRA/DPO recipe produces a GGUF adapter, this renders a Modelfile
that bases off the original Ollama tag, attaches the adapter, and re-applies the
role's system prompt and temperature so the trained model is a drop-in upgrade.
``create_model`` shells out to ``ollama create`` to register it locally.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# Prefix for trained variants so they never shadow the stock model in `ollama list`.
TRAINED_PREFIX = "jimai"


def render_modelfile(
    base: str,
    *,
    adapter_path: str | None = None,
    system_prompt: str = "",
    temperature: float | None = None,
    num_ctx: int | None = None,
) -> str:
    """Render Modelfile text. ``adapter_path`` is the GGUF LoRA produced by training."""
    lines = [f"FROM {base}"]
    if adapter_path:
        lines.append(f"ADAPTER {adapter_path}")
    if temperature is not None:
        lines.append(f"PARAMETER temperature {temperature}")
    if num_ctx is not None:
        lines.append(f"PARAMETER num_ctx {num_ctx}")
    if system_prompt.strip():
        # Triple-quoted SYSTEM block; escape any literal triple-quote in the prompt.
        escaped = system_prompt.replace('"""', '\\"\\"\\"')
        lines.append(f'SYSTEM """{escaped}"""')
    return "\n".join(lines) + "\n"


def trained_tag(base: str, prefix: str = TRAINED_PREFIX) -> str:
    """Derive a safe trained-variant tag, e.g. ``qwen3:8b`` → ``jimai-qwen3:8b``."""
    name, _, tag = base.partition(":")
    return f"{prefix}-{name}:{tag or 'latest'}"


def write_modelfile(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def create_model(tag: str, modelfile_path: Path) -> subprocess.CompletedProcess[str]:
    """Register the trained model with Ollama via ``ollama create``."""
    return subprocess.run(
        ["ollama", "create", tag, "-f", str(modelfile_path)],
        capture_output=True,
        text=True,
        check=False,
    )
