"""Local fine-tuning subsystem.

Turns JimAI's own usage into stronger local models without leaving the
Ollama-only stack: it mines chat history and the self-improve pipeline's
critic/verifier verdicts into SFT + DPO datasets (`dataset`) — optionally
augmented with curated external instruction sets (`sources`) — enumerates every
model in the stack and how each can be trained (`catalog`), emits a QLoRA/DPO
training script per model for a GPU box / WSL2 (`recipe`), and loads the
resulting adapter back into Ollama via a generated Modelfile (`modelfile`).
`pipeline` wires these together; `run` is the CLI entry point. The standalone
GPU-box executables (`scripts.smoke_train`, `scripts.merge_adapter`) live in
`scripts/` — run directly, never imported.

Training and serving stay local and Ollama-only; the lone network touch is
`sources`, which optionally downloads public instruction datasets (no cloud
model provider, no telemetry).
"""
