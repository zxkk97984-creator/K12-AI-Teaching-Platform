#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

gate_state="$(python3 - <<'PY'
import json
from pathlib import Path
state = json.loads(Path('.rebuild-kit/progress.json').read_text(encoding='utf-8'))['gates']
print(state['G_API_CONTRACT']['status'], state['G_LIVE_BUDGET']['status'])
PY
)"
if [ "$gate_state" != "PASS PASS" ]; then
  printf 'BLOCKED: T31 live verification requires G_API_CONTRACT and G_LIVE_BUDGET; current=%s\n' "$gate_state" >&2
  exit 3
fi

: "${KNODO_BASE_URL:?KNODO_BASE_URL is required after the live gates pass}"
: "${KNODO_PAT:?KNODO_PAT is required after the live gates pass}"
: "${KNODO_MAX_REQUESTS:?KNODO_MAX_REQUESTS is required after the live gates pass}"
case "$KNODO_MAX_REQUESTS" in
  ''|*[!0-9]*) echo 'KNODO_MAX_REQUESTS must be a non-negative integer' >&2; exit 2 ;;
esac
if [ "$KNODO_MAX_REQUESTS" -lt 1 ]; then
  echo 'KNODO_MAX_REQUESTS must be at least 1 for a live run' >&2
  exit 2
fi
echo 'Verified gates; live Knodo adapter is intentionally not invoked by this offline-only checkout.' >&2
exit 4
