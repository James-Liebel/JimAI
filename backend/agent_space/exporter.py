"""Export generated apps/modules to a target folder."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .paths import EXPORTS_DIR, PROJECT_ROOT, ensure_layout


def _safe_resolve(base: Path, candidate: str) -> Path:
    path = Path(candidate)
    if not path.is_absolute():
        path = (base / candidate).resolve()
    else:
        path = path.resolve()
    return path


def _copy_item(src: Path, dest: Path) -> None:
    if src.is_dir():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def export_items(target_folder: str, include_paths: list[str], label: str = "") -> dict[str, Any]:
    """Copy selected paths from repo into a target export folder."""
    ensure_layout()
    target_root = _safe_resolve(EXPORTS_DIR, target_folder)
    target_root.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    missing: list[str] = []

    for rel in include_paths:
        src = (PROJECT_ROOT / rel).resolve()
        if not str(src).startswith(str(PROJECT_ROOT.resolve())):
            missing.append(rel)
            continue
        if not src.exists():
            missing.append(rel)
            continue
        dest = (target_root / rel).resolve()
        _copy_item(src, dest)
        copied.append(rel.replace("\\", "/"))

    return {
        "target_folder": str(target_root),
        "label": label,
        "copied": copied,
        "missing": missing,
        "count": len(copied),
    }

