from __future__ import annotations

from sqlalchemy.engine import make_url


class UnsafeTestDatabase(ValueError):
    pass


def validate_test_database_url(value: str | None) -> str:
    if not value:
        raise UnsafeTestDatabase("TEST_DATABASE_URL is required")
    try:
        url = make_url(value)
    except Exception as exc:
        raise UnsafeTestDatabase("TEST_DATABASE_URL is not a valid SQLAlchemy URL") from exc
    if not url.drivername.startswith("postgresql+asyncpg"):
        raise UnsafeTestDatabase("TEST_DATABASE_URL must use postgresql+asyncpg")
    if url.host not in {"127.0.0.1", "localhost"}:
        raise UnsafeTestDatabase("TEST_DATABASE_URL host must be localhost")
    if url.port != 55434:
        raise UnsafeTestDatabase("TEST_DATABASE_URL port must be the isolated 55434 port")
    if not url.database or not url.database.endswith("_test"):
        raise UnsafeTestDatabase("TEST_DATABASE_URL database name must end with _test")
    if not url.username or not url.password:
        raise UnsafeTestDatabase("TEST_DATABASE_URL must include dedicated credentials")
    return value
