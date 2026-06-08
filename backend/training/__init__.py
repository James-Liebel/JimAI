"""Local fine-tuning subsystem.

Turns JimAI's own usage into stronger local models without leaving the
Ollama-only stack: it mines chat history and the self-improve pipeline's
critic/verifier verdicts into SFT + DPO datasets (`dataset`), enumerates every
model in the stack and how each can be trained (`catalog`), emits a QLoRA/DPO
training script per model for a GPU box / WSL2 (`recipe`), and loads the
resulting adapter back into Ollama via a generated Modelfile (`modelfile`).
`pipeline` wires these together; `run` is the CLI entry point.

Nothing here calls the network or a cloud provider — training runs locally and
the output is a normal local Ollama model.
"""
