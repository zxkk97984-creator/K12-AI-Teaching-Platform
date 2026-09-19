from __future__ import annotations

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.core.database import get_engine
from app.main import create_app
from app.modules.identity.models import AuthSession, User
from tests.identity_helpers import ORIGIN, create_synthetic_user, login, write_headers


def _session_cookie(response) -> str:
    for value in response.headers.get_list("set-cookie"):
        if value.startswith("sl_session="):
            return value.split(";", 1)[0].split("=", 1)[1]
    raise AssertionError("session cookie missing")


@pytest.mark.asyncio
async def test_login_me_logout_revokes_old_cookie(client, test_settings: Settings):
    await create_synthetic_user(test_settings, username="student.a", password="Synthetic-A-123")
    response = await login(client, "student.a", "Synthetic-A-123")
    assert response.status_code == 200, response.text
    cookies = response.headers.get_list("set-cookie")
    session_header = next(value for value in cookies if value.startswith("sl_session="))
    csrf_header = next(value for value in cookies if value.startswith("sl_csrf="))
    assert "HttpOnly" in session_header
    assert "HttpOnly" not in csrf_header
    assert "SameSite=lax" in session_header
    assert "Path=/" in session_header
    old_cookie = _session_cookie(response)
    engine = get_engine(test_settings.active_database_url, "test")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        stored = await db.scalar(select(AuthSession.token_hash))
        assert stored != old_cookie
        assert len(stored) == 64
        password_hash = await db.scalar(select(User.password_hash))
        assert password_hash.startswith("$argon2id$")
        assert password_hash != "Synthetic-A-123"

    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "student.a"
    assert me.json()["profile"]["grade"] == 2

    token = response.json()["csrf_token"]
    logged_out = await client.post("/api/v1/auth/logout", headers=write_headers(token))
    assert logged_out.status_code == 204
    assert (await client.get("/api/v1/me")).status_code == 401

    # A saved copy of the old cookie cannot resurrect the revoked server session.
    forged = await client.get("/api/v1/me", headers={"Cookie": f"sl_session={old_cookie}"})
    assert forged.status_code == 401


@pytest.mark.asyncio
async def test_client_selected_session_cookie_is_not_authentication(
    client, test_settings: Settings
):
    await create_synthetic_user(test_settings, username="student.a", password="Synthetic-A-123")
    forged = await client.get("/api/v1/me", headers={"Cookie": "sl_session=client-selected"})
    assert forged.status_code == 401
    response = await login(client, "student.a", "Synthetic-A-123")
    assert response.status_code == 200
    assert _session_cookie(response) != "client-selected"


@pytest.mark.asyncio
async def test_wrong_password_and_disabled_account_do_not_enumerate(
    client, test_settings: Settings
):
    await create_synthetic_user(
        test_settings, username="student.active", password="Synthetic-A-123"
    )
    disabled = await create_synthetic_user(
        test_settings, username="student.disabled", password="Synthetic-A-123"
    )
    engine = get_engine(test_settings.active_database_url, "test")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        await db.execute(update(User).where(User.id == disabled.id).values(is_active=False))
        await db.commit()

    wrong = await login(client, "student.active", "wrong-password")
    inactive = await login(client, "student.disabled", "Synthetic-A-123")
    assert wrong.status_code == inactive.status_code == 401
    assert wrong.json()["error"]["message"] == inactive.json()["error"]["message"]


@pytest.mark.asyncio
async def test_expired_revoked_and_disabled_sessions_are_rejected(app, test_settings: Settings):
    users = {}
    for name, password in [
        ("student.expired", "Expired-Pass-123"),
        ("student.revoked", "Revoked-Pass-123"),
        ("student.disabled-session", "Disabled-Pass-123"),
    ]:
        users[name] = await create_synthetic_user(test_settings, username=name, password=password)

    from httpx import ASGITransport, AsyncClient

    engine = get_engine(test_settings.active_database_url, "test")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    clients: dict[str, AsyncClient] = {}
    for name, password in [
        ("student.expired", "Expired-Pass-123"),
        ("student.revoked", "Revoked-Pass-123"),
        ("student.disabled-session", "Disabled-Pass-123"),
    ]:
        transport = ASGITransport(app=app)
        value = AsyncClient(transport=transport, base_url=ORIGIN)
        response = await login(value, name, password)
        assert response.status_code == 200
        clients[name] = value

    async with factory() as db:
        from datetime import UTC, datetime, timedelta

        sessions = (await db.scalars(select(AuthSession))).all()
        by_user = {str(session.user_id): session for session in sessions}
        expired = by_user[str(users["student.expired"].id)]
        expired.created_at = datetime.now(UTC) - timedelta(hours=2)
        expired.expires_at = datetime.now(UTC) - timedelta(hours=1)
        by_user[str(users["student.revoked"].id)].revoked_at = datetime.now(UTC)
        await db.execute(
            update(User)
            .where(User.id == users["student.disabled-session"].id)
            .values(is_active=False)
        )
        await db.commit()

    for name in clients:
        assert (await clients[name].get("/api/v1/me")).status_code == 401
        await clients[name].aclose()


@pytest.mark.asyncio
async def test_login_rate_limit_uses_configurable_threshold(client, test_settings: Settings):
    await create_synthetic_user(test_settings, username="student.rate", password="Rate-Pass-123")
    limited_settings = test_settings.model_copy(update={"login_rate_limit_attempts": 2})
    limited_app = create_app(limited_settings)
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=limited_app), base_url=ORIGIN
    ) as limited_client:
        first = await login(limited_client, "student.rate", "wrong")
        second = await login(limited_client, "student.rate", "wrong")
        third = await login(limited_client, "student.rate", "Rate-Pass-123")
        assert first.status_code == second.status_code == 401
        assert third.status_code == 429
        assert "Rate-Pass-123" not in third.text


def test_production_requires_secure_cookie_and_https_origin():
    with pytest.raises(ValueError):
        Settings(
            app_env="production",
            app_session_secret="x" * 32,
            database_url="postgresql+asyncpg://u:p@127.0.0.1:55433/db",
            allowed_origins="http://127.0.0.1:15173",
            cookie_secure=True,
        )
    with pytest.raises(ValueError):
        Settings(
            app_env="production",
            app_session_secret="x" * 32,
            database_url="postgresql+asyncpg://u:p@127.0.0.1:55433/db",
            allowed_origins="https://example.test",
            cookie_secure=False,
        )
