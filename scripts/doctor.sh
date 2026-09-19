#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail=0
check() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    printf 'OK   %s\n' "$label"
  else
    printf 'FAIL %s\n' "$label"
    fail=1
  fi
}

check "python3.12" python3.12 --version
check "uv" uv --version
check "node" node --version
check "npm" npm --version
check "docker client" docker --version
check "docker compose" docker compose version
check "docker daemon" docker info

if [ -n "${CODELAB_RUNNER_URL:-}" ]; then
  check "codelab runner control plane" curl -fsS "${CODELAB_RUNNER_URL%/}/health"
else
  printf 'INFO codelab runner is disabled; CodeLab will report UNAVAILABLE\n'
fi

for port in 15173 18081 55433 55434; do
  if timeout 0.3 bash -c "</dev/tcp/127.0.0.1/$port" 2>/dev/null; then
    printf 'INFO port %s is already listening; do not kill it\n' "$port"
  else
    printf 'OK   port %s is available\n' "$port"
  fi
done

if [ -f "$ROOT/.env" ]; then
  printf 'INFO existing .env detected; it will not be overwritten or printed\n'
else
  printf 'INFO no .env present; inject environment variables explicitly\n'
fi
exit "$fail"
