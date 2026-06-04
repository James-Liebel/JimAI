"""Single-origin SPA hosting: backend serves the built frontend with a client-
side-route fallback, without shadowing API/asset 404s. Skips when the frontend
hasn't been built (frontend/dist absent)."""

from __future__ import annotations

from pathlib import Path

import pytest

_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
pytestmark = pytest.mark.skipif(not _DIST.is_dir(), reason="frontend/dist not built")


@pytest.fixture(scope="module")
def client():
    from starlette.testclient import TestClient
    import main

    # No `with` => skip lifespan startup (no Ollama/services needed for routing).
    return TestClient(main.app)


def test_root_serves_spa(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


def test_deep_link_falls_back_to_spa(client):
    # A hard refresh on a client-side route must load the SPA shell, not 404.
    r = client.get("/builder")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


def test_unknown_api_path_keeps_json_404_not_spa(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert "text/html" not in r.headers.get("content-type", "")


def test_missing_asset_404s_not_spa(client):
    # Guards the Windows os.sep normalization: 'assets\\x' must match the prefix.
    r = client.get("/assets/definitely-not-real.js")
    assert r.status_code == 404
    assert "text/html" not in r.headers.get("content-type", "")


def test_health_route_wins_over_static_mount(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert "application/json" in r.headers.get("content-type", "")
