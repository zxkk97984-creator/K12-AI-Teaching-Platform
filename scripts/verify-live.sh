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
  printf 'BLOCKED: live verification requires G_API_CONTRACT and G_LIVE_BUDGET; current=%s\n' "$gate_state" >&2
  exit 3
fi

python3 docs/integrations/knodo/validate_evidence.py
python3 - <<'PY'
import json
from pathlib import Path

evidence = json.loads(Path('docs/acceptance/T31-live-results.synthetic.json').read_text(encoding='utf-8'))
summary = json.loads(Path('docs/acceptance/T31-live-summary.json').read_text(encoding='utf-8'))
ledger = json.loads(Path('storage/private/t31-request-budget.json').read_text(encoding='utf-8'))

if not evidence.get('sequence_complete') or len(evidence.get('records', [])) != 16:
    raise SystemExit('T31 live evidence is incomplete')
if summary.get('recorded_cases') != 16 or summary.get('human_review') != 'NOT_RUN':
    raise SystemExit('T31 summary state is inconsistent')
if ledger.get('authorized_max_requests') != 16 or ledger.get('reserved_requests') != 16:
    raise SystemExit('T31 private ledger is inconsistent')
print('PASS: T31 live evidence is complete; human review remains NOT_RUN.')
PY
