from __future__ import annotations

import os

import pytest

from app.core.test_database import UnsafeTestDatabase, validate_test_database_url


def test_valid_local_test_database() -> None:
    value = os.environ["TEST_DATABASE_URL"]
    assert validate_test_database_url(value) == value


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "sqlite+aiosqlite:///test.db",
        "postgresql+asyncpg://u:p@db.example.com:55434/name_test",
        "postgresql+asyncpg://u:p@127.0.0.1:5432/name_test",
        "postgresql+asyncpg://u:p@127.0.0.1:55434/name_dev",
        "postgresql+asyncpg://u:@127.0.0.1:55434/name_test",
    ],
)
def test_unsafe_database_is_rejected(value: str | None) -> None:
    with pytest.raises(UnsafeTestDatabase):
        validate_test_database_url(value)
