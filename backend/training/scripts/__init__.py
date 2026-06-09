"""Standalone GPU-box executables — run directly, never imported.

Unlike the rest of the package (prep/orchestration that runs inside the app),
these do the heavy CUDA work — LoRA training and adapter merging — so they are
invoked on the machine with the GPU: ``python -m training.scripts.<name>``.
"""
