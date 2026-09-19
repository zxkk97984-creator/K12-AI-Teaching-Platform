"""Shared helpers for T12 conversation/run tests."""

from __future__ import annotations

import os
from typing import Any

import httpx

from app.config import Settings
from app.main import create_app
from app.modules.content.importer import import_package
from app.modules.content.package import load_package
from tests.content_helpers import FIXTURE_PACKAGE, revision_by_slug, sha256_bytes
from tests.identity_helpers import (
    ORIGIN,
    create_synthetic_user,
    csrf,
    login,
    write_headers,
)

__all__ = [
    "ORIGIN",
    "csrf_headers",
    "create_app_client",
    "create_synthetic_user",
    "login",
    "prepare_fixture_course",
    "sha256_bytes",
    "teaching_settings",
    "write_headers",
]


def teaching_settings(test_settings: Settings, **overrides: Any) -> Settings:
    payload: dict[str, Any] = {
        "app_env": "test",
        "app_session_secret": os.environ["APP_SESSION_SECRET"],
        "test_database_url": test_settings.test_database_url,
        "database_url": test_settings.database_url,
        "allowed_origins": "http://127.0.0.1:15173",
        "cookie_secure": False,
        "gateway_mode": "fixture",
        "teaching_autorun": False,
        "gateway_timeout_seconds": 5,
        "teaching_lease_seconds": 60,
        "teaching_sse_poll_seconds": 0.02,
        "teaching_sse_heartbeat_seconds": 30,
    }
    payload.update(overrides)
    return Settings(**payload)


def create_app_client(settings: Settings) -> httpx.AsyncClient:
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:15173")


async def prepare_fixture_course(db, *, chapter_slug: str = "ch01", revision: int = 1):
    await import_package(db, load_package(FIXTURE_PACKAGE), dry_run=False)
    return await revision_by_slug(db, "t06-fixture-course", chapter_slug, revision)


async def csrf_headers(client: httpx.AsyncClient) -> dict[str, str]:
    """Origin + CSRF header bundle for state-changing requests."""

    return write_headers(await csrf(client))
