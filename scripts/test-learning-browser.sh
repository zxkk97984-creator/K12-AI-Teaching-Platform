#!/usr/bin/env bash
# Four-stage browser regression; only the isolated test database is used.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
. scripts/load-runtime-env.sh
export APP_ENV=test GATEWAY_MODE=fixture ALLOWED_ORIGINS=http://localhost:15174
export PYTHONPATH="$ROOT:$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"
for port in 18082 15174; do
  if ss -ltnH "sport = :$port" | rg -q .; then
    printf '端口 %s 已有监听，未启动测试服务。\n' "$port" >&2
    exit 1
  fi
done
QA_STORAGE="${XDG_CACHE_HOME:-$HOME/.cache}/k12/learning-browser-runtime"
install -d -m 700 "$QA_STORAGE"
export RESOURCE_STORAGE_ROOT="$QA_STORAGE/resources"
export AUTHORING_ARTIFACT_ROOT="$QA_STORAGE/authoring"
export AUTHORING_BUNDLE_ROOT="$QA_STORAGE/authoring-bundles"
mkdir -p "$RESOURCE_STORAGE_ROOT" "$AUTHORING_ARTIFACT_ROOT" "$AUTHORING_BUNDLE_ROOT" frontend/test-results/learning-content-browser
QA_API_PID=""; QA_WEB_PID=""
cleanup() {
  [ -z "$QA_WEB_PID" ] || kill "$QA_WEB_PID" 2>/dev/null || true
  [ -z "$QA_API_PID" ] || kill "$QA_API_PID" 2>/dev/null || true
  [ -z "$QA_WEB_PID" ] || wait "$QA_WEB_PID" 2>/dev/null || true
  [ -z "$QA_API_PID" ] || wait "$QA_API_PID" 2>/dev/null || true
  mkdir -p "$ROOT/frontend/test-results/learning-content-browser"
  [ ! -f "$QA_STORAGE/api.log" ] || cp "$QA_STORAGE/api.log" "$ROOT/frontend/test-results/learning-content-browser/api.log"
  [ ! -f "$QA_STORAGE/web.log" ] || cp "$QA_STORAGE/web.log" "$ROOT/frontend/test-results/learning-content-browser/web.log"
}
trap cleanup EXIT
uv run --project backend --locked python -m app.scripts.prepare_learning_browser_test
backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 18082 > "$QA_STORAGE/api.log" 2>&1 &
QA_API_PID=$!
(cd frontend; exec env VITE_API_PROXY_TARGET=http://127.0.0.1:18082 node node_modules/vite/bin/vite.js --config vite.config.ts --host 127.0.0.1 --port 15174) > "$QA_STORAGE/web.log" 2>&1 &
QA_WEB_PID=$!
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:18082/health/ready >/dev/null 2>&1 && curl -fsS http://localhost:15174/login >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:18082/health/ready >/dev/null
cd frontend
HTML_LEARNING_E2E=1 CODELAB_E2E_BASE_URL=http://localhost:15174 ./node_modules/.bin/playwright test --config playwright.config.ts src/e2e/learning-html.spec.ts src/e2e/original-books.spec.ts src/e2e/ai-fruit-trainer.spec.ts src/e2e/autoplay-examples.spec.ts "$@"
