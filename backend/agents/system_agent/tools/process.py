"""Process inspection and management tools."""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime

try:
    import psutil
except ImportError:  # pragma: no cover - dependency guard
    psutil = None


def _require_psutil():
    if psutil is None:
        raise ImportError("psutil is not installed. Add it to the backend environment first.")


@dataclass
class ProcessInfo:
    pid: int
    name: str
    status: str
    cpu_percent: float
    memory_mb: float
    create_time: str
    cmdline: str


def process_info_to_dict(info: ProcessInfo) -> dict:
    return asdict(info)


def list_processes(filter_name: str | None = None) -> list[ProcessInfo]:
    """List running processes, optionally filtered by name."""
    _require_psutil()
    results: list[ProcessInfo] = []
    for proc in psutil.process_iter(
        ["pid", "name", "status", "cpu_percent", "memory_info", "create_time", "cmdline"]
    ):
        try:
            info = proc.info
            name = info.get("name") or ""
            if filter_name and filter_name.lower() not in name.lower():
                continue
            results.append(
                ProcessInfo(
                    pid=int(info.get("pid") or 0),
                    name=name,
                    status=str(info.get("status") or ""),
                    cpu_percent=round(float(info.get("cpu_percent") or 0.0), 1),
                    memory_mb=round(
                        float(getattr(info.get("memory_info"), "rss", 0)) / 1_048_576,
                        1,
                    ),
                    create_time=datetime.fromtimestamp(float(info.get("create_time") or 0)).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    cmdline=" ".join(info.get("cmdline") or [])[:300],
                )
            )
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return sorted(results, key=lambda item: item.memory_mb, reverse=True)


def kill_process(pid: int) -> dict:
    """Terminate a process by PID."""
    _require_psutil()
    try:
        proc = psutil.Process(pid)
        name = proc.name()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except psutil.TimeoutExpired:
            proc.kill()
        return {"pid": pid, "name": name, "killed": True}
    except psutil.NoSuchProcess:
        return {"pid": pid, "killed": False, "reason": "Process not found"}
    except psutil.AccessDenied:
        return {"pid": pid, "killed": False, "reason": "Access denied"}


def get_system_stats() -> dict:
    """Return a compact system resource snapshot."""
    _require_psutil()
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("C:/")
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.4),
        "cpu_cores": psutil.cpu_count(),
        "memory_used_gb": round(memory.used / 1e9, 1),
        "memory_total_gb": round(memory.total / 1e9, 1),
        "memory_percent": round(memory.percent, 1),
        "disk_used_gb": round(disk.used / 1e9, 1),
        "disk_total_gb": round(disk.total / 1e9, 1),
        "disk_percent": round(disk.percent, 1),
        "gpu": _get_gpu_info(),
    }


def _get_gpu_info() -> dict:
    """Read NVIDIA GPU stats via nvidia-smi when available."""
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,name",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            return {}
        parts = [part.strip() for part in completed.stdout.strip().split(",")]
        if len(parts) < 5:
            return {}
        return {
            "utilization_percent": int(parts[0]),
            "memory_used_mb": int(parts[1]),
            "memory_total_mb": int(parts[2]),
            "temperature_c": int(parts[3]),
            "name": parts[4],
        }
    except Exception:
        return {}


def open_application(app_name: str) -> dict:
    """Launch a common application by alias or explicit executable."""
    executable = {
        "calculator": "calc.exe",
        "chrome": "chrome.exe",
        "cursor": "cursor",
        "excel": "EXCEL.EXE",
        "explorer": "explorer.exe",
        "firefox": "firefox.exe",
        "notepad": "notepad.exe",
        "outlook": "OUTLOOK.EXE",
        "paint": "mspaint.exe",
        "powershell": "powershell.exe",
        "terminal": "wt.exe",
        "vscode": "code",
        "word": "WINWORD.EXE",
    }.get(app_name.lower(), app_name)
    subprocess.Popen([executable], shell=True)
    return {"app": app_name, "launched": True}
