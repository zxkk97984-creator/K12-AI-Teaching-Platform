from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import Settings


@lru_cache(maxsize=8)
def get_engine(database_url: str, app_env: str) -> AsyncEngine:
    kwargs: dict[str, object] = {"pool_pre_ping": True}
    if app_env == "test":
        kwargs["poolclass"] = NullPool
    else:
        kwargs.update({"pool_size": 2, "max_overflow": 0})
    return create_async_engine(
        database_url,
        connect_args={"timeout": 2},
        **kwargs,
    )


def engine_for(settings: Settings) -> AsyncEngine:
    return get_engine(settings.active_database_url, settings.app_env)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    settings: Settings = request.app.state.settings
    factory = async_sessionmaker(engine_for(settings), expire_on_commit=False)
    async with factory() as session:
        yield session


async def database_ready(engine: AsyncEngine) -> bool:
    """Readiness includes the identity migration, not only TCP/DB reachability."""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1 FROM identity_users LIMIT 0"))
    except Exception:
        return False
    return True
