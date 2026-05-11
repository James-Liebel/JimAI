from fastapi import FastAPI
from fastapi.testclient import TestClient

from observability.middleware import RequestIdMiddleware


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/x")
    def x():
        return {}

    return app


def test_request_id_minted_when_missing():
    r = TestClient(_make_app()).get("/x")
    assert r.headers.get("x-request-id")


def test_request_id_honoured_when_provided():
    r = TestClient(_make_app()).get("/x", headers={"x-request-id": "abc123"})
    assert r.headers["x-request-id"] == "abc123"
