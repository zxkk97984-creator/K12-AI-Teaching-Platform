#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${POSTGRES_DEV_PASSWORD:?POSTGRES_DEV_PASSWORD is required}"
: "${APP_SESSION_SECRET:?APP_SESSION_SECRET is required}"
: "${E2E_CODELAB_USERNAME:?E2E_CODELAB_USERNAME is required}"
: "${E2E_CODELAB_PASSWORD:?E2E_CODELAB_PASSWORD is required}"
: "${CODELAB_RUNNER_TOKEN:?CODELAB_RUNNER_TOKEN is required}"

export APP_ENV=development
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://k12r1_app:${POSTGRES_DEV_PASSWORD}@127.0.0.1:55433/k12r1_dev}"
export ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-http://127.0.0.1:15173}"
export GATEWAY_MODE=fixture
export CODELAB_RUNNER_URL="${CODELAB_RUNNER_URL:-http://127.0.0.1:18090}"

curl -fsS "$CODELAB_RUNNER_URL/health" >/dev/null
(
  cd backend
  ./.venv/bin/alembic -c alembic.ini upgrade head
  ./.venv/bin/python -m app.modules.codelab.importer
) >/tmp/k12-codelab-import.log

./backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 18081 >/tmp/k12-codelab-api.log 2>&1 &
api_pid=$!
(
  cd frontend
  exec ./node_modules/.bin/vite --config vite.config.ts --host 127.0.0.1 --port 15173
) >/tmp/k12-codelab-vite.log 2>&1 &
web_pid=$!

cleanup() {
  kill "$api_pid" "$web_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:18081/health/ready >/dev/null \
    && curl -fsS http://127.0.0.1:15173/ >/dev/null; then
    break
  fi
  sleep 1
done
curl -fsS http://127.0.0.1:18081/health/ready >/dev/null
curl -fsS http://127.0.0.1:15173/ >/dev/null

E2E_CODELAB_USERNAME="$E2E_CODELAB_USERNAME" \
E2E_CODELAB_PASSWORD="$E2E_CODELAB_PASSWORD" \
  ./frontend/node_modules/.bin/playwright test src/e2e/codelab.spec.ts \
  --config frontend/playwright.config.ts --reporter=line 2>&1 | tee docs/acceptance/T26-browser.log
