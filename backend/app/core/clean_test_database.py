"""Owned, derived migration databases; never reset the normal test database."""

from __future__ import annotations

from contextlib import asynccontextmanager

import asyncpg
from sqlalchemy.engine import make_url

from app.core.test_database import UnsafeTestDatabase, validate_test_database_url


def clean_test_database_url(base_url: str) -> str:
    validate_test_database_url(base_url)
    url = make_url(base_url)
    if url.database.endswith("_clean_test"):
        raise UnsafeTestDatabase("The base must be a normal test database")
    name = url.database.removesuffix("_test") + "_clean_test"
    if len(name.encode()) > 63:
        raise UnsafeTestDatabase("Derived clean database name is too long")
    return url.set(database=name).render_as_string(hide_password=False)


@asynccontextmanager
async def empty_clean_test_schema(base_url: str):
    """Hold a DB lock through reset and upgrades, including subprocess upgrades.

    Precreated databases need no CREATEDB. The legacy single-machine owner may
    create its derived database if missing. Only its owned public schema resets.
    """
    clean_url = clean_test_database_url(base_url)
    name = make_url(clean_url).database
    base = await asyncpg.connect(base_url.replace("postgresql+asyncpg", "postgresql"))
    try:
        exists = await base.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if not exists:
            identifier = '"' + name.replace('"', '""') + '"'
            try:
                await base.execute(f"CREATE DATABASE {identifier}")
            except asyncpg.DuplicateDatabaseError:
                pass
            except asyncpg.InsufficientPrivilegeError as exc:
                raise UnsafeTestDatabase("Precreate the owned clean test database") from exc
    finally:
        await base.close()
    connection = await asyncpg.connect(clean_url.replace("postgresql+asyncpg", "postgresql"))
    try:
        owner = await connection.fetchval(
            "SELECT pg_get_userbyid(datdba) = current_user FROM pg_database "
            "WHERE datname = current_database()"
        )
        if not owner:
            raise UnsafeTestDatabase("Refusing to reset a clean database owned by another role")
        # This connection remains alive while Alembic subprocesses run. Two
        # migration tests targeting the same clean DB must run serially.
        await connection.execute("SELECT pg_advisory_lock(20261002, 1)")
        await connection.execute("DROP SCHEMA IF EXISTS public CASCADE")
        await connection.execute("CREATE SCHEMA public AUTHORIZATION CURRENT_USER")
        yield clean_url
    finally:
        await connection.close()
