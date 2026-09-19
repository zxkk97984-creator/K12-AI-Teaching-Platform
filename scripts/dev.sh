#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${POSTGRES_DEV_PASSWORD:?POSTGRES_DEV_PASSWORD is required}"
: "${POSTGRES_TEST_PASSWORD:?POSTGRES_TEST_PASSWORD is required}"
: "${APP_SESSION_SECRET:?APP_SESSION_SECRET is required}"
export APP_ENV=development
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://k12r1_app:${POSTGRES_DEV_PASSWORD}@127.0.0.1:55433/k12r1_dev}"
export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+asyncpg://k12r1_test:${POSTGRES_TEST_PASSWORD:?POSTGRES_TEST_PASSWORD is required}@127.0.0.1:55434/k12r1_test}"

docker compose up -d postgres-dev postgres-test
(
  cd backend
  uv run --locked alembic -c alembic.ini upgrade head
)
uv run --project backend --locked uvicorn app.main:app --host 127.0.0.1 --port 18081 --reload &
api_pid=$!
npm run dev --prefix frontend &
web_pid=$!
trap 'kill "$api_pid" "$web_pid" 2>/dev/null || true' EXIT INT TERM
wait
