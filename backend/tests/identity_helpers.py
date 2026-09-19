from __future__ import annotations

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.core.database import get_engine
from app.modules.identity.models import (
    PreferredStyle,
    User,
    UserRole,
    VoicePreference,
)
from app.modules.identity.service import create_user

ORIGIN = "http://127.0.0.1:15173"


async def create_synthetic_user(
    settings: Settings,
    *,
    username: str,
    password: str,
    role: UserRole = UserRole.STUDENT,
    stage: str | None = "PRIMARY_LOWER",
    grade: int | None = 2,
    preferred_style: PreferredStyle = PreferredStyle.AUTO,
    interests: list[str] | None = None,
    proactive_guidance_enabled: bool = True,
    voice_preference: VoicePreference = VoicePreference.DISABLED,
) -> User:
    engine = get_engine(settings.active_database_url, "test")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        user = await create_user(
            db,
            username=username,
            password=password,
            role=role,
            stage=stage,
            grade=grade,
            preferred_style=preferred_style,
            interests=interests,
            proactive_guidance_enabled=proactive_guidance_enabled,
            voice_preference=voice_preference,
            settings=settings,
        )
        await db.commit()
        await db.refresh(user)
        return user


async def csrf(client: httpx.AsyncClient) -> str:
    response = await client.get("/api/v1/auth/csrf")
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def write_headers(csrf_token: str) -> dict[str, str]:
    return {"Origin": ORIGIN, "X-CSRF-Token": csrf_token}


async def login(
    client: httpx.AsyncClient,
    username: str,
    password: str,
    *,
    origin: str = ORIGIN,
    csrf_header: str | None = None,
) -> httpx.Response:
    token = csrf_header if csrf_header is not None else await csrf(client)
    return await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
        headers={"Origin": origin, "X-CSRF-Token": token},
    )


def auth_headers(token: str, origin: str = ORIGIN) -> dict[str, str]:
    return {"Origin": origin, "X-CSRF-Token": token}
