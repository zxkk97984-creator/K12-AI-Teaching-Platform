from __future__ import annotations

import pytest

from app.config import Settings
from tests.identity_helpers import ORIGIN, create_synthetic_user, csrf, login


@pytest.mark.asyncio
async def test_missing_or_bad_origin_and_csrf_are_rejected(client, test_settings: Settings):
    await create_synthetic_user(test_settings, username="student.csrf", password="Csrf-Pass-123")
    token = await csrf(client)
    missing_origin = await client.post(
        "/api/v1/auth/login",
        json={"username": "student.csrf", "password": "Csrf-Pass-123"},
        headers={"X-CSRF-Token": token},
    )
    bad_origin = await client.post(
        "/api/v1/auth/login",
        json={"username": "student.csrf", "password": "Csrf-Pass-123"},
        headers={"Origin": "https://evil.example", "X-CSRF-Token": token},
    )
    bad_csrf = await client.post(
        "/api/v1/auth/login",
        json={"username": "student.csrf", "password": "Csrf-Pass-123"},
        headers={"Origin": ORIGIN, "X-CSRF-Token": "wrong"},
    )
    null_origin = await client.post(
        "/api/v1/auth/login",
        json={"username": "student.csrf", "password": "Csrf-Pass-123"},
        headers={"Origin": "null", "X-CSRF-Token": token},
    )
    for response in (missing_origin, bad_origin, bad_csrf, null_origin):
        assert response.status_code == 403, response.text
    valid = await login(client, "student.csrf", "Csrf-Pass-123")
    assert valid.status_code == 200


@pytest.mark.asyncio
async def test_failed_preference_write_has_no_side_effect(client, test_settings: Settings):
    await create_synthetic_user(test_settings, username="student.write", password="Write-Pass-123")
    login_response = await login(client, "student.write", "Write-Pass-123")
    assert login_response.status_code == 200
    token = login_response.json()["csrf_token"]
    before = (await client.get("/api/v1/me")).json()["preferences"]
    response = await client.patch(
        "/api/v1/me/preferences",
        json={"base_revision": before["profile_revision"], "preferred_style": "CODE"},
        headers={"Origin": "https://evil.example", "X-CSRF-Token": token},
    )
    assert response.status_code == 403
    after = (await client.get("/api/v1/me")).json()["preferences"]
    assert after == before
