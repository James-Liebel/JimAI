"""Filesystem tools for the system agent."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

SYSTEM_PROTECTED_PATHS = [
    Path(os.environ.get("WINDIR", "C:/Windows")),
    Path(os.environ.get("WINDIR", "C:/Windows")) / "System32",
    Path("C:/Program Files"),
    Path("C:/Program Files (x86)"),
    Path(os.environ.get("APPDATA", "")) / "Microsoft",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft",
]

USER_PATHS = [
    Path.home() / "Documents",
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home() / "Pictures",
    Path.home() / "Videos",
    Path.home() / "Music",
    Path.home() / "OneDrive",
    Path("C:/Users") / os.environ.get("USERNAME", ""),
]

GRANTED_PATHS: list[Path] = []

TEXT_EXTENSIONS = {
    ".bat",
    ".c",
    ".cfg",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".dockerfile",
    ".env",
    ".gitignore",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".ipynb",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".md",
    ".php",
    ".ps1",
    ".py",
    ".r",
    ".rb",
    ".rs",
    ".scss",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

MAX_RESULTS = 500
MAX_FILE_READ_SIZE = 10 * 1024 * 1024
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "env",
    "node_modules",
    "venv",
}


@dataclass
class FileInfo:
    path: str
    name: str
    extension: str
    size_bytes: int
    size_human: str
    modified: str
    created: str
    is_dir: bool
    line_count: Optional[int] = None
    preview: Optional[str] = None


@dataclass
class SearchResult:
    files: list[FileInfo]
    total_found: int
    searched_path: str
    query: str
    truncated: bool


def normalize_path(path_str: str) -> Path:
    """Expand and resolve a user-provided path."""
    if not str(path_str or "").strip():
        raise ValueError("Path is required")
    return Path(path_str).expanduser().resolve()


def is_protected(path: Path) -> bool:
    """Return True when a path is under a protected system root."""
    resolved = path.resolve()
    for protected in SYSTEM_PROTECTED_PATHS:
        protected_text = str(protected).strip()
        if not protected_text:
            continue
        try:
            resolved.relative_to(protected.resolve())
            return True
        except ValueError:
            continue
    return False


def is_accessible(path: Path) -> bool:
    """Allow user-space paths while denying protected roots."""
    candidate = _nearest_existing_path(path)
    if is_protected(candidate):
        return False
    roots = [root.resolve() for root in USER_PATHS + GRANTED_PATHS if str(root).strip()]
    home = Path.home().resolve()
    try:
        candidate.relative_to(home)
        return True
    except ValueError:
        pass
    for root in roots:
        try:
            candidate.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _nearest_existing_path(path: Path) -> Path:
    candidate = path.resolve()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _ensure_accessible(path: Path) -> None:
    if not is_accessible(path):
        raise PermissionError(f"Access denied: {path}")


def _human_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _safe_read_preview(path: Path, include_preview: bool) -> tuple[Optional[int], Optional[str]]:
    if path.suffix.lower() not in TEXT_EXTENSIONS or path.stat().st_size > MAX_FILE_READ_SIZE:
        return None, None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None, None
    preview = text[:500] if include_preview else None
    return text.count("\n") + 1, preview


def _file_info(path: Path, include_preview: bool = False) -> FileInfo:
    stat = path.stat()
    line_count, preview = (None, None)
    if path.is_file():
        line_count, preview = _safe_read_preview(path, include_preview)
    return FileInfo(
        path=str(path),
        name=path.name,
        extension=path.suffix.lower(),
        size_bytes=stat.st_size,
        size_human=_human_size(stat.st_size),
        modified=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
        created=datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
        is_dir=path.is_dir(),
        line_count=line_count,
        preview=preview,
    )


def file_info_to_dict(info: FileInfo) -> dict:
    return asdict(info)


def search_result_to_dict(result: SearchResult) -> dict:
    return {
        "files": [file_info_to_dict(item) for item in result.files],
        "total_found": result.total_found,
        "searched_path": result.searched_path,
        "query": result.query,
        "truncated": result.truncated,
    }


def search_files(
    root: str,
    pattern: str = "*",
    recursive: bool = True,
    include_extensions: list[str] | None = None,
    exclude_dirs: list[str] | None = None,
    min_size_bytes: int | None = None,
    max_size_bytes: int | None = None,
    modified_after: datetime | None = None,
    content_contains: str | None = None,
) -> SearchResult:
    """Search for filesystem entries matching the provided filters."""
    root_path = normalize_path(root)
    _ensure_accessible(root_path)

    exclude = set(exclude_dirs or DEFAULT_EXCLUDED_DIRS)
    ext_filter = {ext.lower() for ext in (include_extensions or [])}
    results: list[FileInfo] = []
    walker = root_path.rglob if recursive else root_path.glob

    for item in walker(pattern):
        if any(part in exclude for part in item.parts):
            continue
        if item.is_dir():
            continue
        if ext_filter and item.suffix.lower() not in ext_filter:
            continue
        try:
            stat = item.stat()
        except (OSError, PermissionError):
            continue
        if min_size_bytes is not None and stat.st_size < min_size_bytes:
            continue
        if max_size_bytes is not None and stat.st_size > max_size_bytes:
            continue
        if modified_after and datetime.fromtimestamp(stat.st_mtime) < modified_after:
            continue
        if content_contains:
            if item.suffix.lower() not in TEXT_EXTENSIONS or stat.st_size > MAX_FILE_READ_SIZE:
                continue
            try:
                haystack = item.read_text(encoding="utf-8", errors="replace").lower()
            except Exception:
                continue
            if content_contains.lower() not in haystack:
                continue
        results.append(_file_info(item))
        if len(results) >= MAX_RESULTS:
            return SearchResult(
                files=results,
                total_found=len(results),
                searched_path=str(root_path),
                query=pattern,
                truncated=True,
            )

    return SearchResult(
        files=results,
        total_found=len(results),
        searched_path=str(root_path),
        query=pattern,
        truncated=False,
    )


def read_file(path: str, max_chars: int = 50_000) -> dict:
    """Read a text file with a defensive size cap."""
    file_path = normalize_path(path)
    _ensure_accessible(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if file_path.is_dir():
        raise IsADirectoryError(f"Cannot read directory: {file_path}")
    size = file_path.stat().st_size
    if size > MAX_FILE_READ_SIZE:
        raise ValueError(
            f"File too large to read inline ({_human_size(size)}). Use search or chunked reads instead."
        )

    content = file_path.read_text(encoding="utf-8", errors="replace")
    return {
        "path": str(file_path),
        "content": content[:max_chars],
        "total_lines": content.count("\n") + 1,
        "total_chars": len(content),
        "truncated": len(content) > max_chars,
        "encoding": "utf-8",
    }


def write_file(path: str, content: str, overwrite: bool = False) -> dict:
    """Write a text file, optionally backing up an overwritten target."""
    file_path = normalize_path(path)
    if is_protected(file_path):
        raise PermissionError(f"Cannot write to system path: {file_path}")
    _ensure_accessible(file_path)
    if file_path.exists() and not overwrite:
        raise FileExistsError(f"File already exists: {file_path}")

    file_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Optional[Path] = None
    if file_path.exists() and overwrite:
        backup_path = file_path.with_suffix(file_path.suffix + ".bak")
        shutil.copy2(file_path, backup_path)

    file_path.write_text(content, encoding="utf-8")
    return {
        "path": str(file_path),
        "bytes_written": len(content.encode("utf-8")),
        "backup_created": str(backup_path) if backup_path else None,
    }


def _powershell_literal_path(path: Path) -> str:
    return str(path).replace("'", "''")


def delete_file(path: str, recycle: bool = True) -> dict:
    """Delete a file, recycling by default."""
    file_path = normalize_path(path)
    if is_protected(file_path):
        raise PermissionError(f"Cannot delete system path: {file_path}")
    _ensure_accessible(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if file_path.is_dir():
        raise IsADirectoryError(f"Use shell or move tools for directories: {file_path}")

    if recycle:
        command = (
            "Add-Type -AssemblyName Microsoft.VisualBasic; "
            "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile("
            f"'{_powershell_literal_path(file_path)}', "
            "'OnlyErrorDialogs', 'SendToRecycleBin')"
        )
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "Recycle Bin delete failed")
        return {"path": str(file_path), "deleted": True, "recycled": True}

    file_path.unlink()
    return {"path": str(file_path), "deleted": True, "recycled": False, "permanent": True}


def move_file(src: str, dst: str) -> dict:
    """Move or rename a file or directory."""
    src_path = normalize_path(src)
    dst_path = normalize_path(dst)
    if is_protected(src_path) or is_protected(dst_path):
        raise PermissionError("Cannot move protected system paths")
    _ensure_accessible(src_path)
    _ensure_accessible(dst_path)
    if not src_path.exists():
        raise FileNotFoundError(f"Source not found: {src_path}")
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src_path), str(dst_path))
    return {"src": str(src_path), "dst": str(dst_path), "moved": True}


def copy_file(src: str, dst: str) -> dict:
    """Copy a file to a new location."""
    src_path = normalize_path(src)
    dst_path = normalize_path(dst)
    if is_protected(dst_path):
        raise PermissionError(f"Cannot copy into system path: {dst_path}")
    _ensure_accessible(src_path)
    _ensure_accessible(dst_path)
    if not src_path.exists():
        raise FileNotFoundError(f"Source not found: {src_path}")
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dst_path)
    return {"src": str(src_path), "dst": str(dst_path), "copied": True}


def list_directory(path: str, include_preview: bool = False) -> dict:
    """List directory contents with metadata."""
    directory = normalize_path(path)
    _ensure_accessible(directory)
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    items: list[FileInfo] = []
    for item in sorted(directory.iterdir(), key=lambda value: (not value.is_dir(), value.name.lower())):
        try:
            items.append(_file_info(item, include_preview=include_preview))
        except (OSError, PermissionError):
            continue

    return {
        "path": str(directory),
        "items": [file_info_to_dict(item) for item in items],
        "count": len(items),
        "dirs": sum(1 for item in items if item.is_dir),
        "files": sum(1 for item in items if not item.is_dir),
    }


def get_file_hash(path: str) -> dict:
    """Return MD5 and SHA256 hashes for a file."""
    file_path = normalize_path(path)
    _ensure_accessible(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    data = file_path.read_bytes()
    return {
        "path": str(file_path),
        "md5": hashlib.md5(data).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def create_directory(path: str) -> dict:
    """Create a directory and its parents."""
    directory = normalize_path(path)
    if is_protected(directory):
        raise PermissionError(f"Cannot create directory in system path: {directory}")
    _ensure_accessible(directory)
    directory.mkdir(parents=True, exist_ok=True)
    return {"path": str(directory), "created": True}
