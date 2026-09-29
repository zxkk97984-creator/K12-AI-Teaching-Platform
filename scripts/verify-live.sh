#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Validate saved evaluation results; this script makes no live requests.
python3 docs/integrations/knodo/validate_evidence.py
backend/.venv/bin/python evals/review_tools.py check-template
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
