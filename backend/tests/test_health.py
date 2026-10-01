from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_live_uses_valid_request_id() -> None:
    client = TestClient(create_app())
    response = client.get("/health/live", headers={"X-Request-ID": "test-request-1"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-1"
    assert response.json()["status"] == "ok"
    assert response.json()["environment"] == "test"


def test_live_replaces_invalid_request_id() -> None:
    client = TestClient(create_app())
    response = client.get("/health/live", headers={"X-Request-ID": "bad value"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "bad value"


def test_ready_uses_isolated_test_database() -> None:
    client = TestClient(create_app())
    response = client.get("/health/ready")
    assert response.status_code == 200, response.text
    assert response.json()["database"] == "ok"
