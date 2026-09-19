from __future__ import annotations

from fastapi import Query
from fastapi.testclient import TestClient

from app.main import create_app


def test_not_found_has_uniform_envelope() -> None:
    response = TestClient(create_app()).get("/missing", headers={"X-Request-ID": "req-404"})
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["request_id"] == "req-404"
    assert "traceback" not in response.text.lower()


def test_validation_has_uniform_envelope() -> None:
    app = create_app()

    @app.get("/validation-probe")
    async def probe(count: int = Query(..., ge=1)):
        return {"count": count}

    response = TestClient(app).get("/validation-probe?count=0")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
