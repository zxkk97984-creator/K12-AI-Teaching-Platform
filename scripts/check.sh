#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

: "${TEST_DATABASE_URL:?TEST_DATABASE_URL is required; tests refuse non-isolated databases}"
: "${APP_SESSION_SECRET:?APP_SESSION_SECRET is required}"
export APP_ENV=test
APP_SESSION_SECRET="$APP_SESSION_SECRET" uv run --project backend --locked python -c 'from app.core.test_database import validate_test_database_url; import os; validate_test_database_url(os.environ.get("TEST_DATABASE_URL"))'
(
  cd backend
  uv run --locked alembic -c alembic.ini upgrade head
)

python3 .rebuild-kit/tools/validate_kit.py
python3 docs/discovery/validate_pack_integrity.py
python3 docs/discovery/validate_source_audit.py
(
  cd .snapshots/T05-before-20260918
  sha256sum -c SHA256SUMS >/dev/null
)
python3 docs/integrations/knodo/validate_evidence.py
python3 curriculum/planning/validate_plan.py
python3 contracts/test_contracts.py -v
openapi_tmp="$(mktemp)"
(
  cd backend
  uv run --locked python -m app.modules.identity.openapi "$openapi_tmp"
)
diff -u contracts/openapi.identity.json "$openapi_tmp"
uv run --project backend --locked pytest backend/tests -q
uv run --project backend --locked ruff check backend
uv run --project backend --locked ruff format --check backend
npx --prefix frontend openapi-typescript contracts/openapi.identity.json -o /tmp/k12r1-identity.generated.ts >/dev/null
diff -u frontend/src/shared/types/generated/identity.ts /tmp/k12r1-identity.generated.ts
npm test --prefix frontend
npm run typecheck --prefix frontend
npm run build --prefix frontend
printf 'PASS: offline checks completed.\n'
