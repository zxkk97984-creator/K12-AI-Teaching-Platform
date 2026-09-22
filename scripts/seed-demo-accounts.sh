#!/usr/bin/env bash
# Create or reset the local synthetic demo accounts.
#
# The demo accounts are the only accounts a developer needs by hand: browser e2e
# runs and manual demos log in with them. They are synthetic, exist only in the
# local dev database, and are refused in production by the seeding module.
#
# Safe to re-run: existing accounts are reset to the configured password rather
# than left at an unknown value. This is the one place that intentionally
# overwrites a password, which is why it lives in a script rather than in the
# seeding module (whose ensure_demo_user never overwrites).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
. "$ROOT/scripts/load-runtime-env.sh"

: "${POSTGRES_DEV_PASSWORD:?POSTGRES_DEV_PASSWORD is required}"
: "${DEMO_STUDENT_JUNIOR_USERNAME:?DEMO_STUDENT_JUNIOR_USERNAME is required}"
: "${DEMO_STUDENT_LOWER_USERNAME:?DEMO_STUDENT_LOWER_USERNAME is required}"
: "${DEMO_ADMIN_USERNAME:?DEMO_ADMIN_USERNAME is required}"
: "${DEMO_STUDENT_JUNIOR_PASSWORD:?DEMO_STUDENT_JUNIOR_PASSWORD is required}"

export APP_ENV=development
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://k12r1_app:${POSTGRES_DEV_PASSWORD}@127.0.0.1:55433/k12r1_dev}"

cd backend
./.venv/bin/python - <<'PY'
import asyncio, os
from app.config import Settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.modules.identity.models import User, UserRole
from app.modules.identity.security import PasswordManager

# username -> (role, stage, grade, style, interests)
ACCOUNTS = {
    os.environ["DEMO_STUDENT_JUNIOR_USERNAME"]: (
        UserRole.STUDENT, "JUNIOR", 8, "CODE", ["编程", "算法"]),
    os.environ["DEMO_STUDENT_LOWER_USERNAME"]: (
        UserRole.STUDENT, "PRIMARY_LOWER", 2, "STORY", ["机器人", "绘画"]),
    os.environ["DEMO_ADMIN_USERNAME"]: (UserRole.ADMIN, None, None, "AUTO", []),
}
PASSWORDS = {
    os.environ["DEMO_STUDENT_JUNIOR_USERNAME"]: os.environ["DEMO_STUDENT_JUNIOR_PASSWORD"],
    os.environ["DEMO_STUDENT_LOWER_USERNAME"]: os.environ["DEMO_STUDENT_LOWER_PASSWORD"],
    os.environ["DEMO_ADMIN_USERNAME"]: os.environ["DEMO_ADMIN_PASSWORD"],
}

async def main() -> int:
    settings = Settings()
    if settings.app_env == "production":
        raise SystemExit("demo accounts are disabled in production")
    manager = PasswordManager(settings)
    engine = create_async_engine(settings.active_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    missing = []
    async with factory() as db:
        for username, (role, stage, grade, style, interests) in ACCOUNTS.items():
            user = await db.scalar(select(User).where(User.username == username))
            if user is None:
                missing.append(username)
                continue
            user.password_hash = manager.hash(PASSWORDS[username])
            user.is_active = True
            print(f"{username}: password reset, role={role.value}")
        await db.commit()
    await engine.dispose()
    if missing:
        # Creating accounts is the seeding module's job; it also sets the profile.
        raise SystemExit(
            "missing demo accounts: " + ", ".join(missing)
            + "\nRun: cd backend && python -m app.modules.identity.demo"
        )
    return 0

raise SystemExit(asyncio.run(main()))
PY
printf 'PASS: demo accounts are ready; passwords were not printed.\n'
