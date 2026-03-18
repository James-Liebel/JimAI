"""Validation script for Agent Space core workflows."""

from __future__ import annotations

import time
from pathlib import Path
import sys

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from main import app
from agent_space.paths import DATA_ROOT, PROJECT_ROOT

GENERATED_DIR = DATA_ROOT / "generated"
AUTONOMOUS_FILE = GENERATED_DIR / "autonomous_validation.txt"
STOP_TEST_FILE = GENERATED_DIR / "should_not_exist.txt"
GENERATED_REL = str(GENERATED_DIR.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")


def wait_for_run(client: TestClient, run_id: str, timeout: float = 120.0) -> dict:
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
    AUTONOMOUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if AUTONOMOUS_FILE.exists():
        AUTONOMOUS_FILE.unlink()
    if STOP_TEST_FILE.exists():
        STOP_TEST_FILE.unlink()

    with TestClient(app) as client:
        # Power ON baseline
        power_on = client.post("/api/agent-space/power", json={"enabled": True, "release_gpu_on_off": False})
        power_on.raise_for_status()
        print("POWER ON:", power_on.json())

        # Autonomous run -> review gate
        start = client.post(
            "/api/agent-space/runs/start",
            json={
                "objective": f"Create file {GENERATED_REL}/autonomous_validation.txt with autonomous validation output",
                "autonomous": True,
                "review_gate": True,
                "allow_shell": False,
            },
        )
        start.raise_for_status()
        run_summary = start.json()
        run_id = run_summary["id"]
        print("AUTONOMOUS RUN START:", run_summary)

        run_final = wait_for_run(client, run_id)
        print("AUTONOMOUS RUN END:", {"id": run_final["id"], "status": run_final["status"], "reviews": run_final["review_ids"]})

        # Review approve/apply flow
        assert run_final["review_ids"], "Expected a review from autonomous run."
        review_id = run_final["review_ids"][0]
        review_before = client.get(f"/api/agent-space/reviews/{review_id}")
        review_before.raise_for_status()
        print("REVIEW BEFORE:", {"id": review_id, "status": review_before.json()["status"]})

        approve = client.post(f"/api/agent-space/reviews/{review_id}/approve")
        approve.raise_for_status()
        print("REVIEW APPROVED:", {"id": review_id, "status": approve.json()["status"]})

        apply = client.post(f"/api/agent-space/reviews/{review_id}/apply")
        apply.raise_for_status()
        applied = apply.json()
        print("REVIEW APPLIED:", {"id": review_id, "status": applied["status"], "snapshot_id": applied["snapshot_id"]})

        assert AUTONOMOUS_FILE.exists(), "Expected autonomous file to exist after apply."

        # Rollback flow
        rollback = client.post(f"/api/agent-space/rollback/{applied['snapshot_id']}")
        rollback.raise_for_status()
        print("ROLLBACK:", rollback.json())

        assert not AUTONOMOUS_FILE.exists(), "Expected rollback to remove autonomous file."

        # Power OFF blocks new runs
        power_off = client.post("/api/agent-space/power", json={"enabled": False, "release_gpu_on_off": False})
        power_off.raise_for_status()
        print("POWER OFF:", power_off.json())

        blocked = client.post(
            "/api/agent-space/runs/start",
            json={"objective": "this should be blocked", "autonomous": False},
        )
        print("POWER OFF BLOCK CHECK:", {"status_code": blocked.status_code, "body": blocked.json()})
        assert blocked.status_code >= 400

        # Power ON and graceful stop-at-next-step flow
        power_on_again = client.post("/api/agent-space/power", json={"enabled": True, "release_gpu_on_off": False})
        power_on_again.raise_for_status()

        stop_run_start = client.post(
            "/api/agent-space/runs/start",
            json={
                "objective": "Power stop validation run",
                "autonomous": False,
                "review_gate": True,
                "allow_shell": True,
                "command_profile": "safe",
                "subagents": [
                    {
                        "id": "coder",
                        "role": "coder",
                        "depends_on": [],
                        "actions": [
                            {"type": "run_shell", "command": "python -c \"import time; time.sleep(2)\""},
                            {"type": "write_file", "path": f"{GENERATED_REL}/should_not_exist.txt", "content": "stop-test"},
                        ],
                    }
                ],
            },
        )
        stop_run_start.raise_for_status()
        stop_run_id = stop_run_start.json()["id"]
        client.post("/api/agent-space/power", json={"enabled": False, "release_gpu_on_off": False}).raise_for_status()
        stop_run_final = wait_for_run(client, stop_run_id)
        print("POWER STOP RUN:", {"id": stop_run_id, "status": stop_run_final["status"]})
        assert stop_run_final["status"] in {"stopped", "completed"}
        assert not STOP_TEST_FILE.exists(), "Run should stop before second write action."

        # Restore ON for export test
        client.post("/api/agent-space/power", json={"enabled": True, "release_gpu_on_off": False}).raise_for_status()

        export = client.post(
            "/api/agent-space/export",
            json={
                "target_folder": "validation_export",
                "include_paths": ["backend/agent_space", "frontend/src/pages/SelfCode.tsx"],
                "label": "validation-export",
            },
        )
        export.raise_for_status()
        export_data = export.json()
        print("EXPORT:", {"target": export_data["target_folder"], "count": export_data["count"]})
        assert export_data["count"] >= 1

        print("VALIDATION RESULT: PASS")


if __name__ == "__main__":
    main()
