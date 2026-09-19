#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

"$ROOT/scripts/build-runner.sh"
: "${APP_SESSION_SECRET:?APP_SESSION_SECRET is required for the isolated test database}"
: "${TEST_DATABASE_URL:?TEST_DATABASE_URL is required for the isolated test database}"
export RUNNER_DOCKER_TESTS=1
exec "$ROOT/backend/.venv/bin/python" -m pytest backend/tests/integrations/test_runner_docker.py -q
