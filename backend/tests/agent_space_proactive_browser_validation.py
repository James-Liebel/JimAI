"""Validation script for proactive engine and browser APIs."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from main import app


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
    with TestClient(app) as client:
        client.post("/api/agent-space/power", json={"enabled": True, "release_gpu_on_off": False}).raise_for_status()

        existing_goals = client.get("/api/agent-space/proactive/goals?limit=2000")
        existing_goals.raise_for_status()
        for row in list(existing_goals.json() or []):
            goal_id = str(row.get("id", "")).strip()
            if goal_id:
                client.delete(f"/api/agent-space/proactive/goals/{goal_id}").raise_for_status()

        status_before = client.get("/api/agent-space/proactive/status")
        status_before.raise_for_status()
        print("PROACTIVE STATUS BEFORE:", status_before.json())

        goal = client.post(
            "/api/agent-space/proactive/goals",
            json={
                "name": "Validation Proactive Self Improve",
                "objective": "Run self-improvement analysis and propose updates",
                "interval_seconds": 60,
                "enabled": True,
                "run_template": {
                    "autonomous": False,
                    "review_gate": True,
                    "subagents": [
                        {
                            "id": "self-improver",
                            "role": "coder",
                            "depends_on": [],
                            "actions": [{"type": "self_improve"}],
                        }
                    ],
                },
            },
        )
        goal.raise_for_status()
        goal_id = goal.json()["id"]
        print("PROACTIVE GOAL CREATED:", {"id": goal_id})

        tick = client.post("/api/agent-space/proactive/tick")
        tick.raise_for_status()
        tick_data = tick.json()
        print("PROACTIVE TICK:", tick_data)
        assert tick_data["triggered"], "Expected proactive tick to trigger at least one run."
        run_id = next(
            (row["run_id"] for row in tick_data["triggered"] if str(row.get("goal_id")) == goal_id),
            tick_data["triggered"][0]["run_id"],
        )
        run_final = wait_for_run(client, run_id)
        print("PROACTIVE RUN:", {"id": run_id, "status": run_final["status"], "review_ids": run_final["review_ids"]})
        assert run_final["status"] == "completed"

        self_improve = client.post("/api/agent-space/self-improve/run")
        self_improve.raise_for_status()
        self_run_id = self_improve.json()["id"]
        self_final = wait_for_run(client, self_run_id)
        print("SELF IMPROVE RUN:", {"id": self_run_id, "status": self_final["status"]})

        browser_open = client.post(
            "/api/agent-space/browser/sessions",
            json={"url": "https://example.com", "headless": True},
        )
        browser_open.raise_for_status()
        browser_data = browser_open.json()
        print("BROWSER OPEN:", {"success": browser_data.get("success"), "error": browser_data.get("error", "")[:120]})
        if browser_data.get("success"):
            session_id = browser_data["session_id"]
            state = client.get(f"/api/agent-space/browser/sessions/{session_id}/state?include_links=true&link_limit=20")
            state.raise_for_status()
            state_data = state.json()
            print(
                "BROWSER STATE:",
                {
                    "success": state_data.get("success"),
                    "url": state_data.get("url", "")[:120],
                    "link_count": len(state_data.get("links", [])),
                },
            )
            move = client.post(
                f"/api/agent-space/browser/sessions/{session_id}/cursor/move",
                json={"x": 100, "y": 120, "steps": 1},
            )
            move.raise_for_status()
            print("BROWSER CURSOR MOVE:", {"success": move.json().get("success")})
            click = client.post(
                f"/api/agent-space/browser/sessions/{session_id}/cursor/click",
                json={"button": "left", "click_count": 1},
            )
            click.raise_for_status()
            print("BROWSER CURSOR CLICK:", {"success": click.json().get("success")})
            scroll = client.post(
                f"/api/agent-space/browser/sessions/{session_id}/cursor/scroll",
                json={"dy": 300},
            )
            scroll.raise_for_status()
            print("BROWSER CURSOR SCROLL:", {"success": scroll.json().get("success")})
            extract = client.post(
                f"/api/agent-space/browser/sessions/{session_id}/extract",
                json={"selector": "body", "max_chars": 500},
            )
            extract.raise_for_status()
            extract_data = extract.json()
            print("BROWSER EXTRACT:", {"success": extract_data.get("success"), "text_len": len(extract_data.get("text", ""))})
            close = client.post(f"/api/agent-space/browser/sessions/{session_id}/close")
            close.raise_for_status()
            print("BROWSER CLOSE:", close.json())
        else:
            assert browser_data.get("error"), "Expected graceful browser error when unavailable."

        client.delete(f"/api/agent-space/proactive/goals/{goal_id}").raise_for_status()
        print("PROACTIVE+BROWSER VALIDATION RESULT: PASS")


if __name__ == "__main__":
    main()
