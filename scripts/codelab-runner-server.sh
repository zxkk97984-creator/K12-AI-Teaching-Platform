#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
: "${RUNNER_CONTROL_TOKEN:?RUNNER_CONTROL_TOKEN is required}"
exec "$ROOT/backend/.venv/bin/python" -m runner.host.server
