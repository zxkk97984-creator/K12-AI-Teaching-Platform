#!/usr/bin/env bash
# Real configured teachers and memory assistant; all local writes use the isolated test DB.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
. scripts/load-runtime-env.sh
export PYTHONPATH="$ROOT:$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"

K12_ACCEPTANCE_SNAPSHOT="$(mktemp)"
chmod 600 "$K12_ACCEPTANCE_SNAPSHOT"
export K12_ACCEPTANCE_SNAPSHOT
trap 'rm -f "$K12_ACCEPTANCE_SNAPSHOT"' EXIT

uv run --project backend --locked python - <<'PY'
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path("backend").resolve()))
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.config import Settings
from app.core.database import get_engine
from app.core.test_database import validate_test_database_url
from app.modules.ai.service import registry

async def main():
    validate_test_database_url(os.environ.get("TEST_DATABASE_URL"))
    if not os.environ.get("KNODO_PAT"):
        raise SystemExit("Configure KNODO_PAT in the private runtime file first.")
    supplied = os.environ.get("K12_AI_REGISTRY_SNAPSHOT_INPUT")
    if supplied:
        source = Path(supplied)
        if not source.is_absolute() or not source.is_file():
            raise SystemExit("Registry snapshot must be an existing absolute private file.")
        stat = source.stat()
        if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
            raise SystemExit("Registry snapshot must be owned by this user with mode 600.")
        snapshot = json.loads(source.read_text(encoding="utf-8"))
        from app.modules.ai.schemas import RegistryData
        RegistryData.model_validate(snapshot["data"])
        if not snapshot.get("persisted") or not isinstance(snapshot.get("revision"), int):
            raise SystemExit("Registry snapshot must contain a persisted registry revision.")
        Path(os.environ["K12_ACCEPTANCE_SNAPSHOT"]).write_text(
            json.dumps(snapshot, ensure_ascii=False), encoding="utf-8"
        )
        return
    settings = Settings()
    engine = get_engine(settings.active_database_url, settings.app_env)
    try:
        async with async_sessionmaker(engine)() as db:
            snapshot = await registry(db, settings)
        if not snapshot["persisted"]:
            raise SystemExit("Save the AI registry first, or supply K12_AI_REGISTRY_SNAPSHOT_INPUT (private mode 600).")
        Path(os.environ["K12_ACCEPTANCE_SNAPSHOT"]).write_text(
            json.dumps(snapshot, ensure_ascii=False), encoding="utf-8"
        )
    finally:
        await engine.dispose()

asyncio.run(main())
PY

cd backend
APP_ENV=test K12_KNODO_LIVE_ACCEPTANCE=1 K12_AI_REGISTRY_SNAPSHOT="$K12_ACCEPTANCE_SNAPSHOT" \
    uv run --locked pytest tests/test_knodo_live_ai_memory.py -q -s --tb=short
