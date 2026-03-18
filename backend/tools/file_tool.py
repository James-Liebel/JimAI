"""File system tool — read, write, list, search with safety guards."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Only allow operations within the project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _is_safe_path(path: Path) -> bool:
    """Check that a path is within the project root."""
    try:
        resolved = path.resolve()
        return str(resolved).startswith(str(_PROJECT_ROOT))
    except Exception:
        return False


async def read(path: str) -> str:
    """Read a file's contents."""
    p = Path(path)
    if not _is_safe_path(p):
        return f"Access denied: {path} is outside the project directory"
    if not p.exists():
        return f"File not found: {path}"
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"Error reading {path}: {exc}"


async def write(path: str, content: str) -> str:
    """Write content to a file (only in approved directories)."""
    p = Path(path)
    if not _is_safe_path(p):
        return f"Access denied: {path} is outside the project directory"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Written {len(content)} chars to {path}"
    except Exception as exc:
        return f"Error writing {path}: {exc}"


async def list_dir(path: str) -> list[str]:
    """List directory contents."""
    p = Path(path)
    if not _is_safe_path(p):
        return [f"Access denied: {path}"]
    if not p.is_dir():
        return [f"Not a directory: {path}"]
    try:
        return sorted(str(item.relative_to(p)) for item in p.iterdir())
    except Exception as exc:
        return [f"Error: {exc}"]


async def search_files(directory: str, pattern: str) -> list[str]:
    """Glob search for files matching a pattern."""
    p = Path(directory)
    if not _is_safe_path(p):
        return [f"Access denied: {directory}"]
    try:
        return sorted(str(f) for f in p.rglob(pattern))[:50]
    except Exception as exc:
        return [f"Error: {exc}"]


async def get_tree(path: str, max_depth: int = 3) -> str:
    """Return a tree-like string representation of a directory."""
    p = Path(path)
    if not _is_safe_path(p):
        return f"Access denied: {path}"

    lines: list[str] = [p.name + "/"]

    def _walk(dir_path: Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        except PermissionError:
            return

        # Skip common uninteresting dirs
        skip = {"node_modules", ".git", "__pycache__", ".venv", "dist", "chroma_db"}
        entries = [e for e in entries if e.name not in skip]

        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            if entry.is_dir():
                lines.append(f"{prefix}{connector}{entry.name}/")
                extension = "    " if is_last else "│   "
                _walk(entry, prefix + extension, depth + 1)
            else:
                lines.append(f"{prefix}{connector}{entry.name}")

    _walk(p, "", 0)
    return "\n".join(lines)
