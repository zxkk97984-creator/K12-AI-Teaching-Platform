from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.core.database import get_engine
from app.modules.identity.models import LearnerProfile, UserRole
from tests.identity_helpers import ORIGIN, create_synthetic_user, login, write_headers


async def _login_profile(client, username: str, password: str):
    response = await login(client, username, password)
    assert response.status_code == 200, response.text
    return response.json()


async def _patch(client, path: str, payload: dict, token: str):
    return await client.patch(path, json=payload, headers=write_headers(token))


@pytest.mark.asyncio
async def test_stage_boundaries_and_nullable_grade(client, test_settings: Settings):
    await create_synthetic_user(
        test_settings,
        username="student.boundaries",
        password="Boundary-Pass-123",
        stage=None,
        grade=None,
    )
    data = await _login_profile(client, "student.boundaries", "Boundary-Pass-123")
    revision = data["profile"]["revision"]
    token = data["csrf_token"]
    expected = {
        1: "PRIMARY_LOWER",
        3: "PRIMARY_LOWER",
        4: "PRIMARY_UPPER",
        6: "PRIMARY_UPPER",
        7: "JUNIOR",
        9: "JUNIOR",
        10: "SENIOR",
        12: "SENIOR",
    }
    for grade, stage in expected.items():
        response = await _patch(
            client,
            "/api/v1/me/profile",
            {"base_revision": revision, "stage": stage, "grade": grade},
            token,
        )
        assert response.status_code == 200, response.text
        revision = response.json()["profile"]["revision"]
        assert response.json()["profile"]["grade"] == grade
        assert response.json()["profile"]["stage"] == stage

    null_grade = await _patch(
        client,
        "/api/v1/me/profile",
        {"base_revision": revision, "stage": "JUNIOR", "grade": None},
        token,
    )
    assert null_grade.status_code == 200
    assert null_grade.json()["profile"]["grade"] is None
    assert null_grade.json()["profile"]["stage"] == "JUNIOR"


@pytest.mark.asyncio
async def test_stage_only_switch_clears_old_grade_and_style_survives_reload(
    client, test_settings: Settings
):
    await create_synthetic_user(
        test_settings,
        username="student.stage-switch",
        password="Stage-Switch-Pass-123",
        stage="PRIMARY_LOWER",
        grade=2,
    )
    data = await _login_profile(client, "student.stage-switch", "Stage-Switch-Pass-123")
    switched = await _patch(
        client,
        "/api/v1/me/profile",
        {"base_revision": data["profile"]["revision"], "stage": "SENIOR"},
        data["csrf_token"],
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["profile"]["stage"] == "SENIOR"
    assert switched.json()["profile"]["grade"] is None

    styled = await _patch(
        client,
        "/api/v1/me/preferences",
        {
            "base_revision": switched.json()["profile"]["revision"],
            "preferred_style": "STEP_BY_STEP",
        },
        data["csrf_token"],
    )
    assert styled.status_code == 200, styled.text
    reloaded = await client.get("/api/v1/me")
    assert reloaded.status_code == 200
    assert reloaded.json()["profile"]["stage"] == "SENIOR"
    assert reloaded.json()["profile"]["grade"] is None
    assert reloaded.json()["preferences"]["preferred_style"] == "STEP_BY_STEP"


@pytest.mark.asyncio
async def test_invalid_or_conflicting_grade_is_rejected_without_side_effect(
    client, test_settings: Settings
):
    await create_synthetic_user(
        test_settings,
        username="student.invalid-grade",
        password="Invalid-Pass-123",
        stage="PRIMARY_LOWER",
        grade=2,
    )
    data = await _login_profile(client, "student.invalid-grade", "Invalid-Pass-123")
    revision = data["profile"]["revision"]
    token = data["csrf_token"]
    for payload in [
        {"base_revision": revision, "grade": 0},
        {"base_revision": revision, "grade": 13},
        {"base_revision": revision, "grade": "5"},
        {"base_revision": revision, "stage": "SENIOR", "grade": 2},
    ]:
        response = await _patch(client, "/api/v1/me/profile", payload, token)
        assert response.status_code == 422, (payload, response.text)

    engine = get_engine(test_settings.active_database_url, "test")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        profile = await db.scalar(
            select(LearnerProfile).where(LearnerProfile.user_id == data["user"]["id"])
        )
        assert profile.grade == 2
        assert profile.stage == "PRIMARY_LOWER"
        assert profile.revision == revision


@pytest.mark.asyncio
async def test_student_cannot_use_admin_or_forge_identity_fields(
    app, client, test_settings: Settings
):
    student = await create_synthetic_user(
        test_settings, username="student.a", password="Student-A-Pass-123"
    )
    other = await create_synthetic_user(
        test_settings, username="student.b", password="Student-B-Pass-123"
    )
    admin = await create_synthetic_user(
        test_settings,
        username="admin.c",
        password="Admin-C-Pass-123",
        role=UserRole.ADMIN,
        stage=None,
        grade=None,
    )
    data = await _login_profile(client, "student.a", "Student-A-Pass-123")
    assert (await client.get("/api/v1/admin/identity/status")).status_code == 403
    forged = await _patch(
        client,
        "/api/v1/me/preferences",
        {"base_revision": data["profile"]["revision"], "preferred_style": "CODE", "role": "admin"},
        data["csrf_token"],
    )
    assert forged.status_code == 422
    engine = get_engine(test_settings.active_database_url, "test")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        other_profile = await db.scalar(
            select(LearnerProfile).where(LearnerProfile.user_id == other.id)
        )
        assert other_profile.preferred_style == "AUTO"
        assert other_profile.revision == 0
    me_with_query = await client.get(f"/api/v1/me?user_id={other.id}")
    assert me_with_query.status_code == 200
    assert me_with_query.json()["user"]["id"] == str(student.id)

    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as admin_client:
        admin_login = await login(admin_client, "admin.c", "Admin-C-Pass-123")
        assert admin_login.status_code == 200
        status_response = await admin_client.get("/api/v1/admin/identity/status")
        assert status_response.status_code == 200
        assert status_response.json()["role"] == "admin"
        assert "username" not in status_response.text
    assert admin.role == "admin"


@pytest.mark.asyncio
async def test_preferences_partial_patch_revision_and_persistence(client, test_settings: Settings):
    await create_synthetic_user(
        test_settings,
        username="student.pref",
        password="Preference-Pass-123",
        preferred_style="AUTO",
        interests=["绘画"],
        proactive_guidance_enabled=True,
    )
    data = await _login_profile(client, "student.pref", "Preference-Pass-123")
    revision = data["profile"]["revision"]
    token = data["csrf_token"]

    first = await _patch(
        client,
        "/api/v1/me/preferences",
        {"base_revision": revision, "preferred_style": "STEP_BY_STEP"},
        token,
    )
    assert first.status_code == 200
    revision = first.json()["preferences"]["profile_revision"]
    second = await _patch(
        client,
        "/api/v1/me/preferences",
        {"base_revision": revision, "interests": ["算法", "机器人"]},
        token,
    )
    assert second.status_code == 200
    prefs = second.json()["preferences"]
    assert prefs["preferred_style"] == "STEP_BY_STEP"
    assert prefs["interests"] == ["算法", "机器人"]
    revision = prefs["profile_revision"]

    null_preference = await _patch(
        client,
        "/api/v1/me/preferences",
        {"base_revision": revision, "preferred_style": None},
        token,
    )
    assert null_preference.status_code == 422

    stale = await _patch(
        client,
        "/api/v1/me/preferences",
        {"base_revision": revision - 1, "voice_preference": "INPUT_ONLY"},
        token,
    )
    assert stale.status_code == 409
    after_stale = await client.get("/api/v1/me")
    assert after_stale.json()["preferences"]["profile_revision"] == revision

    logout = await client.post("/api/v1/auth/logout", headers=write_headers(token))
    assert logout.status_code == 204
    relogin = await login(client, "student.pref", "Preference-Pass-123")
    assert relogin.status_code == 200
    restored = await client.get("/api/v1/me")
    assert restored.json()["preferences"]["preferred_style"] == "STEP_BY_STEP"
    assert restored.json()["preferences"]["interests"] == ["算法", "机器人"]


@pytest.mark.asyncio
async def test_teacher_style_and_pet_are_separate_account_preferences(
    client, test_settings: Settings
):
    await create_synthetic_user(
        test_settings,
        username="student.teacher-style",
        password="Preference-Pass-123",
        stage="PRIMARY_UPPER",
        grade=5,
    )
    data = await _login_profile(client, "student.teacher-style", "Preference-Pass-123")
    changed = await _patch(
        client,
        "/api/v1/me/preferences",
        {
            "base_revision": data["profile"]["revision"],
            "teacher_style": "SOCRATIC",
            "companion_pet_id": "anya",
        },
        data["csrf_token"],
    )
    assert changed.status_code == 200, changed.text
    reloaded = (await client.get("/api/v1/me")).json()
    assert reloaded["preferences"]["teacher_style"] == "SOCRATIC"
    assert reloaded["preferences"]["companion_pet_id"] == "anya"
    assert reloaded["preferences"]["preferred_style"] == "AUTO"
    rejected = await _patch(
        client,
        "/api/v1/me/preferences",
        {"base_revision": reloaded["profile"]["revision"], "companion_pet_id": "foreign"},
        data["csrf_token"],
    )
    assert rejected.status_code == 422
