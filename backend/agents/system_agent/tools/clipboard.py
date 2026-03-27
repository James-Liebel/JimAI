"""Clipboard access helpers."""

from __future__ import annotations

import subprocess


def read_clipboard() -> str:
    """Read text from the Windows clipboard."""
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Clipboard read failed")
    return completed.stdout.strip()


def write_clipboard(text: str) -> dict:
    """Write text into the Windows clipboard."""
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Set-Clipboard -Value ([Console]::In.ReadToEnd())",
        ],
        input=text,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "Clipboard write failed")
    return {"written": True, "chars": len(text)}
