#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${POSTGRES_DEV_PASSWORD:?POSTGRES_DEV_PASSWORD is required}"
: "${POSTGRES_TEST_PASSWORD:?POSTGRES_TEST_PASSWORD is required}"
: "${APP_SESSION_SECRET:?APP_SESSION_SECRET is required}"
export APP_ENV=development
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://k12r1_app:${POSTGRES_DEV_PASSWORD}@127.0.0.1:55433/k12r1_dev}"
export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+asyncpg://k12r1_test:${POSTGRES_TEST_PASSWORD}@127.0.0.1:55434/k12r1_test}"

"$ROOT/scripts/doctor.sh"
uv lock --project backend
uv sync --project backend --locked
if [ -f frontend/package-lock.json ]; then
  npm ci --prefix frontend
else
  npm install --prefix frontend
fi
docker compose up -d postgres-dev postgres-test

for service in postgres-dev postgres-test; do
  container_id="$(docker compose ps -q "$service")"
  [ -n "$container_id" ] || { echo "no container for $service" >&2; exit 1; }
  state=""
  for _ in $(seq 1 45); do
    state="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
    [ "$state" = "healthy" ] && break
    sleep 1
  done
  [ "$state" = "healthy" ] || { echo "service not healthy: $service ($state)" >&2; exit 1; }
done
(
  cd backend
  uv run --locked alembic -c alembic.ini upgrade head
)
printf 'PASS: isolated dependencies and PostgreSQL services are ready.\n'
