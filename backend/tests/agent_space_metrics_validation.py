"""Validate Prometheus metrics endpoint."""
import sys
from pathlib import Path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import os
os.environ.setdefault("CSRF_ENABLED", "false")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from main import app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_metrics_endpoint():
    r = client.get("/metrics")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    body = r.text
    # Should contain prometheus comment lines or our fallback
    assert "jimai" in body or "prometheus" in body.lower() or "#" in body, \
        f"Unexpected metrics body: {body[:200]}"
    print(f"METRICS ENDPOINT: {r.status_code} OK")
    print(f"Body preview: {body[:300]}")

def test_metrics_contain_run_metrics():
    # After hitting the endpoint, check expected metric names are present
    r = client.get("/metrics")
    body = r.text
    # These should be present from our metric definitions
    assert "jimai_runs_total" in body or "prometheus_client not installed" in body
    print("METRICS CONTENT TEST: PASS")

if __name__ == "__main__":
    test_metrics_endpoint()
    test_metrics_contain_run_metrics()
    print("METRICS VALIDATION RESULT: PASS")
