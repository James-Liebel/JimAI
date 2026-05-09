"""SupplyChainSentinel — CVE scanner for pip and npm dependencies.

Runs ``pip-audit`` (Python) and ``npm audit`` (Node) as background
subprocesses, parses their JSON output, persists a baseline so subsequent
runs can show *new* findings only, and exposes both stats and a
diff-against-baseline view to the API.

External tool dependency:

    * ``pip-audit`` is recommended (``pip install pip-audit``). If not
      installed the Python scan is skipped.
    * ``npm audit`` is bundled with Node, so works out of the box.

If neither tool is available, the sentinel still loads and reports an
empty status; nothing breaks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..paths import DATA_ROOT, PROJECT_ROOT

logger = logging.getLogger(__name__)


SENTINEL_DIR = DATA_ROOT / "security"
LATEST_FILE = SENTINEL_DIR / "supply_chain_latest.json"
BASELINE_FILE = SENTINEL_DIR / "supply_chain_baseline.json"

# Bound subprocess runtime so the scanner never hangs the platform.
PIP_AUDIT_TIMEOUT_SECONDS = 120
NPM_AUDIT_TIMEOUT_SECONDS = 120


@dataclass
class CveFinding:
    package: str
    ecosystem: str  # "pypi" | "npm"
    installed_version: str
    cve_ids: list[str] = field(default_factory=list)
    advisory_ids: list[str] = field(default_factory=list)
    severity: str = "unknown"
    summary: str = ""
    fix_versions: list[str] = field(default_factory=list)

    def key(self) -> str:
        cve = self.cve_ids[0] if self.cve_ids else (self.advisory_ids[0] if self.advisory_ids else "")
        return f"{self.ecosystem}:{self.package}@{self.installed_version}::{cve}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _have_tool(name: str) -> bool:
    return shutil.which(name) is not None


async def _run_subprocess(args: list[str], *, cwd: Path, timeout: int) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, "", f"subprocess timed out after {timeout}s"
    return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")


def _parse_pip_audit(payload: str) -> list[CveFinding]:
    if not payload.strip():
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    findings: list[CveFinding] = []
    rows: list[dict[str, Any]] = []
    if isinstance(data, dict):
        rows = list(data.get("dependencies") or [])
    elif isinstance(data, list):
        rows = data
    for row in rows:
        if not isinstance(row, dict):
            continue
        package = str(row.get("name") or row.get("package") or "")
        version = str(row.get("version") or row.get("installed_version") or "")
        vulns = row.get("vulns") or row.get("vulnerabilities") or []
        if not isinstance(vulns, list):
            continue
        for vuln in vulns:
            if not isinstance(vuln, dict):
                continue
            advisory_id = str(vuln.get("id") or "")
            aliases = vuln.get("aliases") or []
            cve_ids = [str(a) for a in aliases if isinstance(a, str) and a.upper().startswith("CVE-")]
            findings.append(
                CveFinding(
                    package=package,
                    ecosystem="pypi",
                    installed_version=version,
                    cve_ids=cve_ids,
                    advisory_ids=[advisory_id] if advisory_id else [],
                    severity=str(vuln.get("severity") or "unknown"),
                    summary=str(vuln.get("description") or "")[:400],
                    fix_versions=[str(v) for v in (vuln.get("fix_versions") or []) if isinstance(v, str)],
                )
            )
    return findings


def _parse_npm_audit(payload: str) -> list[CveFinding]:
    if not payload.strip():
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    findings: list[CveFinding] = []
    if not isinstance(data, dict):
        return findings
    advisories = data.get("vulnerabilities")
    if not isinstance(advisories, dict):
        return findings
    for package, info in advisories.items():
        if not isinstance(info, dict):
            continue
        severity = str(info.get("severity") or "unknown")
        version = str(info.get("range") or info.get("via") or "")
        if isinstance(info.get("via"), list):
            via_summary = ", ".join(str(v.get("title") or v.get("name") or "") for v in info["via"] if isinstance(v, dict))
            cve_ids = [
                str(v.get("source") or "")
                for v in info["via"]
                if isinstance(v, dict) and isinstance(v.get("source"), (int, str))
            ]
        else:
            via_summary = ""
            cve_ids = []
        fix_versions: list[str] = []
        fix_payload = info.get("fixAvailable")
        if isinstance(fix_payload, dict):
            fix_versions = [str(fix_payload.get("version") or "")]
        elif isinstance(fix_payload, str):
            fix_versions = [fix_payload]
        findings.append(
            CveFinding(
                package=package,
                ecosystem="npm",
                installed_version=version,
                cve_ids=[c for c in cve_ids if c],
                advisory_ids=[],
                severity=severity,
                summary=via_summary[:400],
                fix_versions=[v for v in fix_versions if v],
            )
        )
    return findings


class SupplyChainSentinel:
    """Cron-style CVE scanner. Call :meth:`scan_now` to run on demand."""

    def __init__(
        self,
        *,
        project_root: Path = PROJECT_ROOT,
        latest_file: Path = LATEST_FILE,
        baseline_file: Path = BASELINE_FILE,
    ) -> None:
        self.project_root = Path(project_root)
        self.latest_file = Path(latest_file)
        self.baseline_file = Path(baseline_file)
        self.latest_file.parent.mkdir(parents=True, exist_ok=True)

    async def scan_now(self) -> dict[str, Any]:
        started_at = time.time()
        results: dict[str, Any] = {
            "started_at": started_at,
            "ended_at": 0.0,
            "ecosystems": {},
            "findings": [],
            "errors": [],
        }
        py_findings: list[CveFinding] = []
        npm_findings: list[CveFinding] = []

        if _have_tool("pip-audit"):
            try:
                rc, stdout, stderr = await _run_subprocess(
                    ["pip-audit", "--format", "json"],
                    cwd=self.project_root / "backend",
                    timeout=PIP_AUDIT_TIMEOUT_SECONDS,
                )
                if rc not in {0, 1}:
                    results["errors"].append({"tool": "pip-audit", "rc": rc, "stderr": stderr[:600]})
                py_findings = _parse_pip_audit(stdout)
                results["ecosystems"]["pypi"] = {
                    "tool": "pip-audit",
                    "rc": rc,
                    "count": len(py_findings),
                }
            except Exception as exc:
                logger.warning("pip-audit failed: %s", exc)
                results["errors"].append({"tool": "pip-audit", "error": str(exc)})
                results["ecosystems"]["pypi"] = {"tool": "pip-audit", "error": str(exc)}
        else:
            results["ecosystems"]["pypi"] = {"tool": "pip-audit", "skipped": "not installed"}

        npm_dir = self.project_root / "frontend"
        if _have_tool("npm") and (npm_dir / "package.json").exists():
            try:
                rc, stdout, stderr = await _run_subprocess(
                    ["npm", "audit", "--json"],
                    cwd=npm_dir,
                    timeout=NPM_AUDIT_TIMEOUT_SECONDS,
                )
                npm_findings = _parse_npm_audit(stdout)
                results["ecosystems"]["npm"] = {
                    "tool": "npm",
                    "rc": rc,
                    "count": len(npm_findings),
                }
            except Exception as exc:
                logger.warning("npm audit failed: %s", exc)
                results["errors"].append({"tool": "npm", "error": str(exc)})
                results["ecosystems"]["npm"] = {"tool": "npm", "error": str(exc)}
        else:
            results["ecosystems"]["npm"] = {"tool": "npm", "skipped": "not installed or no package.json"}

        all_findings = [*py_findings, *npm_findings]
        results["findings"] = [f.to_dict() for f in all_findings]
        results["ended_at"] = time.time()
        results["duration_seconds"] = round(results["ended_at"] - started_at, 3)

        try:
            self.latest_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("failed to persist latest sentinel report: %s", exc)

        return results

    def latest(self) -> dict[str, Any]:
        if not self.latest_file.exists():
            return {"started_at": 0.0, "findings": [], "ecosystems": {}}
        try:
            return json.loads(self.latest_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"started_at": 0.0, "findings": [], "ecosystems": {}}

    def baseline(self) -> dict[str, Any]:
        if not self.baseline_file.exists():
            return {"started_at": 0.0, "keys": []}
        try:
            return json.loads(self.baseline_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"started_at": 0.0, "keys": []}

    def update_baseline(self) -> dict[str, Any]:
        latest = self.latest()
        keys = sorted({CveFinding(**row).key() for row in latest.get("findings", []) if isinstance(row, dict)})
        baseline = {
            "started_at": time.time(),
            "based_on_latest_at": latest.get("started_at", 0.0),
            "keys": keys,
        }
        try:
            self.baseline_file.write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("failed to persist sentinel baseline: %s", exc)
        return baseline

    def diff_vs_baseline(self) -> dict[str, Any]:
        latest = self.latest()
        baseline_keys = set(self.baseline().get("keys") or [])
        new_findings: list[dict[str, Any]] = []
        resolved_keys: list[str] = []
        latest_keys: set[str] = set()
        for row in latest.get("findings", []):
            if not isinstance(row, dict):
                continue
            try:
                finding = CveFinding(**row)
            except TypeError:
                continue
            key = finding.key()
            latest_keys.add(key)
            if key not in baseline_keys:
                new_findings.append(row)
        for key in baseline_keys - latest_keys:
            resolved_keys.append(key)
        return {
            "based_on_latest_at": latest.get("started_at", 0.0),
            "new_count": len(new_findings),
            "resolved_count": len(resolved_keys),
            "new_findings": new_findings,
            "resolved_keys": resolved_keys,
        }

    def stats(self) -> dict[str, Any]:
        latest = self.latest()
        diff = self.diff_vs_baseline()
        return {
            "last_scan_at": latest.get("started_at", 0.0),
            "last_scan_duration": latest.get("duration_seconds", 0.0),
            "total_findings": len(latest.get("findings", [])),
            "ecosystems": latest.get("ecosystems", {}),
            "new_vs_baseline": diff["new_count"],
            "resolved_vs_baseline": diff["resolved_count"],
            "tools_present": {
                "pip-audit": _have_tool("pip-audit"),
                "npm": _have_tool("npm"),
            },
        }
