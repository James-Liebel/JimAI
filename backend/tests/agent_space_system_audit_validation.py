"""Validation script for the Agent Space system-audit endpoint."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from main import app


def main() -> None:
    with TestClient(app) as client:
        quick = client.get("/api/agent-space/admin/system-audit")
        quick.raise_for_status()
        quick_data = quick.json()
        print("AUDIT QUICK:", {"overall_status": quick_data.get("overall_status"), "summary": quick_data.get("summary")})
        assert isinstance(quick_data.get("checks"), list)
        assert any(str(row.get("id")) == "ollama" for row in quick_data.get("checks", []))
        assert any(str(row.get("id")) == "policy" for row in quick_data.get("checks", []))

        deep = client.get("/api/agent-space/admin/system-audit?include_research_probe=true&include_browser_probe=true")
        deep.raise_for_status()
        deep_data = deep.json()
        print("AUDIT DEEP:", {"overall_status": deep_data.get("overall_status"), "summary": deep_data.get("summary")})
        check_ids = {str(row.get("id")) for row in deep_data.get("checks", [])}
        assert "web-research" in check_ids
        assert "browser" in check_ids

        print("SYSTEM AUDIT VALIDATION RESULT: PASS")


if __name__ == "__main__":
    main()
