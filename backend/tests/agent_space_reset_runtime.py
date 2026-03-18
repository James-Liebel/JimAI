"""Reset Agent Space runtime data via API for local cleanup."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import app


def main() -> None:
    with TestClient(app) as client:
        resp = client.post(
            "/api/agent-space/admin/reset-data",
            json={
                "clear_reviews": True,
                "clear_runs": True,
                "clear_snapshots": True,
                "clear_logs": True,
                "clear_memory": True,
                "clear_index": True,
                "clear_chats": True,
                "clear_runtime": True,
                "clear_generated": True,
                "clear_self_improvement": True,
                "clear_proactive_goals": True,
                "clear_teams": False,
                "clear_exports": False,
                "reset_settings": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        print("RESET RESULT:", data)


if __name__ == "__main__":
    main()
