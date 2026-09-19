#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${TEST_DATABASE_URL:?TEST_DATABASE_URL is required}"
: "${APP_SESSION_SECRET:?APP_SESSION_SECRET is required}"
: "${DATABASE_URL:?DATABASE_URL is required for browser verification}"
: "${E2E_T22_REVISION:?E2E_T22_REVISION is required for authoring browser verification}"

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export APP_ENV=test

python3 .rebuild-kit/tools/validate_kit.py
python3 contracts/test_contracts.py -v
backend/.venv/bin/pytest backend/tests -q
npm test --prefix frontend
npm run typecheck --prefix frontend
npm run build --prefix frontend

export APP_ENV=development
export GATEWAY_MODE=fixture
export TEACHING_AUTORUN=true
export AUTHORING_AUTORUN=true
export TEACHING_FIXTURE_DELAY_SECONDS="${TEACHING_FIXTURE_DELAY_SECONDS:-1}"
export CODELAB_RUNNER_URL="${CODELAB_RUNNER_URL:-http://127.0.0.1:18090}"
export CODELAB_RUNNER_TOKEN="${CODELAB_RUNNER_TOKEN:?CODELAB_RUNNER_TOKEN is required}"
export ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-http://127.0.0.1:15173}"

backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 18081 >/tmp/k12-t30-api.log 2>&1 &
api_pid=$!
(
  cd frontend
  exec ./node_modules/.bin/vite --config vite.config.ts --host 127.0.0.1 --port 15173
) >/tmp/k12-t30-vite.log 2>&1 &
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

export E2E_STUDENT_A_USERNAME="${E2E_STUDENT_A_USERNAME:?E2E_STUDENT_A_USERNAME is required}"
export E2E_STUDENT_A_PASSWORD="${E2E_STUDENT_A_PASSWORD:?E2E_STUDENT_A_PASSWORD is required}"
export E2E_STUDENT_B_USERNAME="${E2E_STUDENT_B_USERNAME:?E2E_STUDENT_B_USERNAME is required}"
export E2E_STUDENT_B_PASSWORD="${E2E_STUDENT_B_PASSWORD:?E2E_STUDENT_B_PASSWORD is required}"
export E2E_T20_ADMIN="${E2E_T20_ADMIN:?E2E_T20_ADMIN is required}"
export E2E_T20_ADMIN_PASSWORD="${E2E_T20_ADMIN_PASSWORD:?E2E_T20_ADMIN_PASSWORD is required}"
export E2E_T20_STUDENT="${E2E_T20_STUDENT:?E2E_T20_STUDENT is required}"
export E2E_T20_STUDENT_PASSWORD="${E2E_T20_STUDENT_PASSWORD:?E2E_T20_STUDENT_PASSWORD is required}"
export E2E_T20_SENIOR="${E2E_T20_SENIOR:?E2E_T20_SENIOR is required}"
export E2E_T20_SENIOR_PASSWORD="${E2E_T20_SENIOR_PASSWORD:?E2E_T20_SENIOR_PASSWORD is required}"
export E2E_T21_STUDENT="${E2E_T21_STUDENT:?E2E_T21_STUDENT is required}"
export E2E_T21_STUDENT_PASSWORD="${E2E_T21_STUDENT_PASSWORD:?E2E_T21_STUDENT_PASSWORD is required}"
export E2E_T21_JUNIOR="${E2E_T21_JUNIOR:?E2E_T21_JUNIOR is required}"
export E2E_T21_JUNIOR_PASSWORD="${E2E_T21_JUNIOR_PASSWORD:?E2E_T21_JUNIOR_PASSWORD is required}"
export E2E_T22_ADMIN="${E2E_T22_ADMIN:?E2E_T22_ADMIN is required}"
export E2E_T22_ADMIN_PASSWORD="${E2E_T22_ADMIN_PASSWORD:?E2E_T22_ADMIN_PASSWORD is required}"
export E2E_T22_STUDENT="${E2E_T22_STUDENT:?E2E_T22_STUDENT is required}"
export E2E_T22_STUDENT_PASSWORD="${E2E_T22_STUDENT_PASSWORD:?E2E_T22_STUDENT_PASSWORD is required}"
export E2E_LEARN_USERNAME="${E2E_LEARN_USERNAME:-$E2E_STUDENT_A_USERNAME}"
export E2E_LEARN_PASSWORD="${E2E_LEARN_PASSWORD:-$E2E_STUDENT_A_PASSWORD}"
export E2E_CODELAB_USERNAME="${E2E_CODELAB_USERNAME:?E2E_CODELAB_USERNAME is required}"
export E2E_CODELAB_PASSWORD="${E2E_CODELAB_PASSWORD:?E2E_CODELAB_PASSWORD is required}"

./frontend/node_modules/.bin/playwright test src/e2e \
  --config frontend/playwright.config.ts --reporter=line
