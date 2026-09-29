#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
: "${RUNNER_CONTROL_TOKEN:?RUNNER_CONTROL_TOKEN is required}"
export RUNNER_HOST="${RUNNER_HOST:-127.0.0.1}"
export RUNNER_PORT="${RUNNER_PORT:-18090}"
export RUNNER_IMAGE="${RUNNER_IMAGE:-k12-codelab-runner:0.1.0}"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$ROOT/backend/.venv/bin/python" -m runner.host.server
