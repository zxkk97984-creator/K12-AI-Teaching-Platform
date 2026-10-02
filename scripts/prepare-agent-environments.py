#!/usr/bin/env python3
"""A1-only provisioning on the dedicated test instance. Credentials stay private.

Run with the original runtime file loaded, using backend/.venv/bin/python.
Existing roles/databases are only reused after checking the matching private
configuration and ownership; passwords and existing data are never replaced.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import sys
from pathlib import Path

import asyncpg
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.test_database import validate_test_database_url  # noqa: E402


async def main():
    admin_url = validate_test_database_url(os.environ.get("TEST_DATABASE_URL"))
    config_root = Path.home() / ".config/k12/agents"
    config_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = await asyncpg.connect(admin_url.replace("postgresql+asyncpg", "postgresql"))
    try:
        if not await connection.fetchval(
            "SELECT rolsuper FROM pg_roles WHERE rolname=current_user"
        ):
            raise RuntimeError("A1 must load the test-instance administrator configuration")
        for number in range(1, 7):
            agent = f"a{number}"
            role = f"k12_{agent}"
            databases = [f"k12_{agent}_test", f"k12_{agent}_clean_test"]
            target = config_root / f"{agent}.env"
            role_exists = await connection.fetchval("SELECT 1 FROM pg_roles WHERE rolname=$1", role)
            owners = await connection.fetch(
                "SELECT datname, pg_get_userbyid(datdba) AS owner FROM pg_database "
                "WHERE datname=ANY($1::text[])",
                databases,
            )
            if target.exists():
                if target.stat().st_mode & 0o077:
                    raise RuntimeError(f"Private config permissions are unsafe: {target}")
                values = dict(
                    line.split("=", 1)
                    for line in target.read_text().splitlines()
                    if line and not line.startswith("#")
                )
                configured = make_url(validate_test_database_url(values.get("TEST_DATABASE_URL")))
                if configured.username != role or configured.database != databases[0]:
                    raise RuntimeError(f"Existing config has another target: {target}")
                password = configured.password
            elif role_exists or owners:
                raise RuntimeError(
                    f"Existing {agent} resources lack a matching config; left intact"
                )
            else:
                password = secrets.token_urlsafe(36)
                storage = Path.home() / f".local/share/k12/agents/{agent}"
                state = Path.home() / f".local/state/k12/agents/{agent}"
                qa = state / "qa"
                for directory in (storage, state, qa):
                    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
                url = make_url(admin_url).set(
                    username=role, password=password, database=databases[0]
                )
                web, api = 15200 + number, 18100 + number
                values = {
                    "APP_ENV": "test",
                    "GATEWAY_MODE": "fixture",
                    "DATABASE_URL": url.render_as_string(hide_password=False),
                    "TEST_DATABASE_URL": url.render_as_string(hide_password=False),
                    "APP_SESSION_SECRET": secrets.token_urlsafe(48),
                    "COOKIE_SECURE": "false",
                    "K12_RUNTIME_STORAGE_ROOT": str(storage),
                    "K12_RUNTIME_STATE_DIR": str(state),
                    "QA_RUNTIME_DIR": str(qa),
                    "QA_WEB_PORT": str(web),
                    "QA_API_PORT": str(api),
                    "QA_ISOLATED": "1",
                    "ALLOWED_ORIGINS": f"http://127.0.0.1:{web}",
                    "VITE_API_PROXY_TARGET": f"http://127.0.0.1:{api}",
                    "KNODO_PAT": "",
                    "CODELAB_RUNNER_URL": "",
                    "CODELAB_RUNNER_TOKEN": "",
                }
                with os.fdopen(
                    os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w"
                ) as output:
                    output.write("".join(f"{key}={value}\n" for key, value in values.items()))
            if any(row["owner"] != role for row in owners):
                raise RuntimeError(
                    f"Existing {agent} database belongs to another role; left intact"
                )
            if not role_exists:
                # Generated password is URL-safe. Values never enter shell arguments or logs.
                await connection.execute(
                    f"CREATE ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    f"NOREPLICATION PASSWORD '{password}'"
                )
            flags = await connection.fetchrow(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication "
                "FROM pg_roles WHERE rolname=$1",
                role,
            )
            if any(flags.values()):
                raise RuntimeError(f"Existing {agent} role is overprivileged; left intact")
            if await connection.fetchval(
                "SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles "
                "WHERE rolname=$1)",
                role,
            ):
                raise RuntimeError(f"Existing {agent} role has memberships; left intact")
            for name in databases:
                if not any(row["datname"] == name for row in owners):
                    await connection.execute(f"CREATE DATABASE {name} OWNER {role}")
                # Only the newly assigned Agent DBs are touched. Original DB ACLs stay intact.
                await connection.execute(f"REVOKE ALL ON DATABASE {name} FROM PUBLIC")
                await connection.execute(f"GRANT CONNECT, TEMPORARY ON DATABASE {name} TO {role}")
            probe = await asyncpg.connect(
                make_url(admin_url)
                .set(username=role, password=password, database=databases[0])
                .render_as_string(hide_password=False)
                .replace("postgresql+asyncpg", "postgresql")
            )
            await probe.close()
            print(
                f"{agent}: {databases[0]} / {databases[1]}, "
                f"web={15200 + number}, api={18100 + number}, test/fixture, config={target}"
            )
    finally:
        await connection.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (asyncpg.PostgresError, OSError, ValueError, RuntimeError):
        # Driver errors can contain connection details. Keep credentials out of terminal output.
        raise SystemExit(
            "Agent provisioning failed; resources/configs preserved. Inspect privately."
        ) from None
