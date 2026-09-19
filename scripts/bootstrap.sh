#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${POSTGRES_DEV_PASSWORD:?POSTGRES_DEV_PASSWORD is required}"
: "${POSTGRES_TEST_PASSWORD:?POSTGRES_TEST_PASSWORD is required}"
: "${APP_SESSION_SECRET:?APP_SESSION_SECRET is required}"
export APP_ENV="${APP_ENV:-development}"
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
npm run build --prefix frontend
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
  uv run --locked python -m app.scripts.import_content import \
    --release-dir ../curriculum/source/legacy/k12-library-696364f --apply \
    --mirror-dir ../curriculum/releases
  if [ "$APP_ENV" != "production" ]; then
    uv run --locked python -m app.scripts.import_content import \
      --release-dir ../curriculum/source/synthetic/t06-fixtures-v1 --apply \
      --mirror-dir ../curriculum/releases
  fi
  uv run --locked python -m app.modules.codelab.importer --catalog-root ../curriculum/code-tasks
  if [ "$APP_ENV" != "production" ] && [ -n "${T05_DEMO_STUDENT_A_USERNAME:-}" ] \
    && [ -n "${T05_DEMO_STUDENT_A_PASSWORD:-}" ] \
    && [ -n "${T05_DEMO_STUDENT_B_USERNAME:-}" ] \
    && [ -n "${T05_DEMO_STUDENT_B_PASSWORD:-}" ] \
    && [ -n "${T05_DEMO_ADMIN_USERNAME:-}" ] \
    && [ -n "${T05_DEMO_ADMIN_PASSWORD:-}" ]; then
    uv run --locked python -m app.modules.identity.demo
  else
    printf 'INFO synthetic demo accounts skipped; set T05_DEMO_* variables to provision them.\n'
  fi
)
if [ "${BOOTSTRAP_DEPLOY:-0}" = "1" ]; then
  docker compose up -d --build api worker web
  printf 'PASS: API, worker and web services started; runner is %s.\n' \
    "${CODELAB_RUNNER_URL:-disabled}"
fi
printf 'PASS: isolated dependencies and PostgreSQL services are ready.\n'
