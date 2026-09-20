#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "usage: $0 <completed-review.json> [result.json]" >&2
  exit 2
fi

review_path="$1"
result_path="${2:-docs/acceptance/T31-human-review.result.json}"

if [ ! -f "$review_path" ]; then
  echo "completed review does not exist: $review_path" >&2
  exit 2
fi

backend/.venv/bin/python evals/review_tools.py check-review \
  --review "$review_path" \
  --output "$result_path" >/dev/null

./scripts/verify-live.sh
python3 .rebuild-kit/tools/validate_kit.py
python3 contracts/test_contracts.py -v
git diff --check

conclusion="$(python3 - "$result_path" <<'PY'
import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print(result.get('overall_conclusion', ''))
PY
)"

if [ "$conclusion" != "PASS" ]; then
  printf 'BLOCKED: human review conclusion is %s; T31/T33 cannot be released.\n' "$conclusion" >&2
  exit 4
fi

echo "PASS: human review and T31 technical evidence validate; T33 still requires explicit user sign-off."
