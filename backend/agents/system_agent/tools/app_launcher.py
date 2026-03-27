"""Helpers for launching files and applications."""

from __future__ import annotations

import os

from . import filesystem, process


def launch_application(app_name: str) -> dict:
    """Launch an application alias."""
    return process.open_application(app_name)


def open_path(path: str) -> dict:
    """Open a file or directory with the OS default handler."""
    target = filesystem.normalize_path(path)
    if filesystem.is_protected(target):
        raise PermissionError(f"Cannot open protected system path: {target}")
    if not filesystem.is_accessible(target):
        raise PermissionError(f"Access denied: {target}")
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {target}")
    os.startfile(str(target))
    return {"path": str(target), "opened": True}
