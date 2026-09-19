#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${TEST_DATABASE_URL:?TEST_DATABASE_URL is required}"
: "${APP_SESSION_SECRET:?APP_SESSION_SECRET is required}"
: "${T05_DEMO_STUDENT_A_USERNAME:?T05_DEMO_STUDENT_A_USERNAME is required}"
: "${T05_DEMO_STUDENT_A_PASSWORD:?T05_DEMO_STUDENT_A_PASSWORD is required}"
: "${T05_DEMO_STUDENT_B_USERNAME:?T05_DEMO_STUDENT_B_USERNAME is required}"
: "${T05_DEMO_STUDENT_B_PASSWORD:?T05_DEMO_STUDENT_B_PASSWORD is required}"

export APP_ENV=test
uv run --project backend --locked python -c 'from app.core.test_database import validate_test_database_url; import os; validate_test_database_url(os.environ.get("TEST_DATABASE_URL"))'
(
  cd backend
  uv run --locked alembic -c alembic.ini upgrade head
  uv run --locked python -m app.modules.identity.demo
)
uv run --project backend --locked uvicorn app.main:app --host 127.0.0.1 --port 18081 &
api_pid=$!
(
  cd frontend
  exec ./node_modules/.bin/vite --config vite.config.ts --host 127.0.0.1 --port 15173
) &
web_pid=$!
cleanup() {
  kill "$api_pid" "$web_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:18081/health/ready >/dev/null && curl -fsS http://127.0.0.1:15173/ >/dev/null; then
    break
  fi
  sleep 1
done
curl -fsS http://127.0.0.1:18081/health/ready >/dev/null
curl -fsS http://127.0.0.1:15173/ >/dev/null
E2E_STUDENT_A_USERNAME="$T05_DEMO_STUDENT_A_USERNAME"     E2E_STUDENT_A_PASSWORD="$T05_DEMO_STUDENT_A_PASSWORD"     E2E_STUDENT_B_USERNAME="$T05_DEMO_STUDENT_B_USERNAME"     E2E_STUDENT_B_PASSWORD="$T05_DEMO_STUDENT_B_PASSWORD"     npm run test:e2e:identity --prefix frontend
