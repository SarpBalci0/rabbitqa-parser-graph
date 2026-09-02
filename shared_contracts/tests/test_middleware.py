"""Unit test for shared_contracts.py.middleware (T009) — previously untested, found
during a spec-code synchronization audit."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared_contracts.py.errors import install_error_handlers
from shared_contracts.py.middleware import TracingMiddleware


def _build_app():
    app = FastAPI()
    app.add_middleware(TracingMiddleware)
    install_error_handlers(app)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    @app.post("/mutate")
    def mutate():
        return {"ok": True}

    return app


def test_get_request_gets_trace_id_header():
    client = TestClient(_build_app())
    response = client.get("/ping")
    assert response.status_code == 200
    assert "x-trace-id" in response.headers


def test_mutating_request_without_idempotency_key_is_rejected():
    client = TestClient(_build_app())
    response = client.post("/mutate")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "missing_idempotency_key"


def test_mutating_request_with_idempotency_key_succeeds():
    client = TestClient(_build_app())
    response = client.post("/mutate", headers={"Idempotency-Key": "abc123"})
    assert response.status_code == 200
