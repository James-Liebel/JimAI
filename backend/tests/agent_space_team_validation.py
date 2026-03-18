"""Validation script for Agent Space team/subagent communication."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from main import app
from agent_space.paths import DATA_ROOT, PROJECT_ROOT

GENERATED_DIR = DATA_ROOT / "generated"
TEAM_FILE = GENERATED_DIR / "team_message_validation.txt"
GENERATED_REL = str(GENERATED_DIR.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")


def wait_for_run(client: TestClient, run_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/api/agent-space/runs/{run_id}")
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") in {"completed", "failed", "stopped"}:
            return data
        time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for run {run_id}")


def main() -> None:
    timeout_seconds = float(os.getenv("AGENT_SPACE_TEAM_VALIDATION_TIMEOUT", "120"))
    TEAM_FILE.parent.mkdir(parents=True, exist_ok=True)
    if TEAM_FILE.exists():
        TEAM_FILE.unlink()

    with TestClient(app) as client:
        client.post("/api/agent-space/power", json={"enabled": True, "release_gpu_on_off": False}).raise_for_status()

        team = client.post(
            "/api/agent-space/teams",
            json={
                "name": "Validation Team",
                "description": "Team messaging validation",
                "agents": [
                    {
                        "id": "planner",
                        "role": "coder",
                        "depends_on": [],
                        "actions": [
                            {
                                "type": "send_message",
                                "to": "coder",
                                "channel": "handoff",
                                "content": "Create the team message validation file.",
                            }
                        ],
                    },
                    {
                        "id": "coder",
                        "role": "coder",
                        "depends_on": ["planner"],
                        "actions": [
                            {"type": "read_messages", "channel": "handoff"},
                            {
                                "type": "write_file",
                                "path": f"{GENERATED_REL}/team_message_validation.txt",
                                "content": "created by team communication run",
                            },
                            {
                                "type": "send_message",
                                "to": "tester",
                                "channel": "handoff",
                                "content": "File created. Validate read.",
                            },
                        ],
                    },
                    {
                        "id": "tester",
                        "role": "tester",
                        "depends_on": ["coder"],
                        "actions": [{"type": "read_messages", "channel": "handoff"}],
                    },
                ],
            },
        )
        team.raise_for_status()
        team_data = team.json()
        team_id = team_data["id"]
        print("TEAM CREATED:", {"id": team_id, "name": team_data["name"], "agent_count": len(team_data["agents"])})

        start = client.post(
            "/api/agent-space/runs/start",
            json={
                "objective": "Run team messaging validation workflow",
                "autonomous": False,
                "review_gate": True,
                "team_id": team_id,
            },
        )
        start.raise_for_status()
        run_id = start.json()["id"]
        final = wait_for_run(client, run_id, timeout=timeout_seconds)
        print("TEAM RUN:", {"id": run_id, "status": final["status"], "review_ids": final["review_ids"]})
        assert final["status"] == "completed"

        run_messages = client.get(f"/api/agent-space/runs/{run_id}/messages?limit=200")
        run_messages.raise_for_status()
        msg_rows = run_messages.json()
        print("RUN MESSAGES:", {"count": len(msg_rows)})
        assert any(str(row.get("from")) == "planner" for row in msg_rows), "Expected planner message."
        assert any(str(row.get("from")) == "coder" for row in msg_rows), "Expected coder message."

        team_messages = client.get(f"/api/agent-space/teams/{team_id}/messages?run_id={run_id}&limit=200")
        team_messages.raise_for_status()
        team_rows = team_messages.json()
        print("TEAM MESSAGE ARCHIVE:", {"count": len(team_rows)})
        assert len(team_rows) >= 2

        assert final["review_ids"], "Expected review for write_file action."
        review_id = final["review_ids"][0]
        client.post(f"/api/agent-space/reviews/{review_id}/approve").raise_for_status()
        applied = client.post(f"/api/agent-space/reviews/{review_id}/apply")
        applied.raise_for_status()
        snapshot_id = applied.json()["snapshot_id"]
        print("TEAM REVIEW APPLIED:", {"review_id": review_id, "snapshot_id": snapshot_id})

        assert TEAM_FILE.exists(), "Expected team-created file after apply."
        client.post(f"/api/agent-space/rollback/{snapshot_id}").raise_for_status()
        assert not TEAM_FILE.exists(), "Expected rollback to remove team-created file."

        print("TEAM COMM VALIDATION RESULT: PASS")


if __name__ == "__main__":
    main()
