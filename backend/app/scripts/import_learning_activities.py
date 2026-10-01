"""Import the repository's offline learning packages using the configured demo admin."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.core.database import get_engine
from app.modules.identity.models import User
from app.modules.interactive.learning_bundle import import_learning_activities


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--admin-username", default=os.environ.get("T05_DEMO_ADMIN_USERNAME") or "demo_admin"
    )
    parser.add_argument(
        "--upgrade-from",
        type=Path,
        help="已备份的旧内置课件源目录；仅升级匹配模板，保留当前台词与音频",
    )
    args = parser.parse_args()
    settings = Settings()
    engine = get_engine(settings.active_database_url, settings.app_env)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            statement = select(User).where(User.role == "admin")
            username = args.admin_username
            if username:
                statement = statement.where(User.username == username)
            admins = list(await db.scalars(statement.limit(2)))
            if len(admins) != 1:
                raise SystemExit("Configure/seed the demo admin before importing activities")
            print(
                json.dumps(
                    await import_learning_activities(
                        db, actor=admins[0], settings=settings, upgrade_from=args.upgrade_from
                    ),
                    ensure_ascii=False,
                )
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
