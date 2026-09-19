#!/usr/bin/env python3
"""Idempotently provision synthetic accounts. Never resets existing accounts."""

from __future__ import annotations

import argparse
import asyncio
import os

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.core.database import get_engine
from app.modules.identity.models import PreferredStyle, UserRole
from app.modules.identity.service import ensure_demo_user


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return value


async def _run() -> int:
    settings = Settings()
    if settings.app_env == "production":
        raise SystemExit("demo accounts are disabled in production")
    engine = get_engine(settings.active_database_url, settings.app_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    accounts = [
        {
            "prefix": "T05_DEMO_STUDENT_A",
            "role": UserRole.STUDENT,
            "stage": "PRIMARY_LOWER",
            "grade": 2,
            "preferred_style": PreferredStyle.STORY,
            "interests": ["机器人", "绘画"],
        },
        {
            "prefix": "T05_DEMO_STUDENT_B",
            "role": UserRole.STUDENT,
            "stage": "JUNIOR",
            "grade": 8,
            "preferred_style": PreferredStyle.CODE,
            "interests": ["编程", "算法"],
        },
        {
            "prefix": "T05_DEMO_ADMIN",
            "role": UserRole.ADMIN,
            "stage": None,
            "grade": None,
            "preferred_style": PreferredStyle.AUTO,
            "interests": [],
        },
    ]
    async with factory() as db:
        for account in accounts:
            prefix = account.pop("prefix")
            username = _required(f"{prefix}_USERNAME")
            password = _required(f"{prefix}_PASSWORD")
            _, created = await ensure_demo_user(
                db,
                username=username,
                password=password,
                settings=settings,
                **account,
            )
            print(f"{username}: {'created' if created else 'preserved'}")
    await engine.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="only validate environment")
    args = parser.parse_args()
    if args.check:
        Settings()
        return 0
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
