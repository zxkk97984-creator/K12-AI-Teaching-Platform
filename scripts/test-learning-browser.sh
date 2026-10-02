#!/usr/bin/env bash
# Four-stage browser regression; only the isolated test database is used.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
. scripts/load-runtime-env.sh
. scripts/qa-runtime.sh
export APP_ENV=test GATEWAY_MODE=fixture
export PYTHONPATH="$ROOT:$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"
for port in "$QA_API_PORT" "$QA_WEB_PORT"; do
  if ss -ltnH "sport = :$port" | rg -q .; then
    printf '端口 %s 已有监听，未启动测试服务。\n' "$port" >&2
    exit 1
  fi
done
install -d -m 700 "$QA_RUNTIME_DIR"
mkdir -p "$RESOURCE_STORAGE_ROOT" "$AUTHORING_ARTIFACT_ROOT" "$AUTHORING_BUNDLE_ROOT" frontend/test-results/learning-content-browser
QA_API_PID=""; QA_WEB_PID=""
cleanup() {
  [ -z "$QA_WEB_PID" ] || kill "$QA_WEB_PID" 2>/dev/null || true
  [ -z "$QA_API_PID" ] || kill "$QA_API_PID" 2>/dev/null || true
  [ -z "$QA_WEB_PID" ] || wait "$QA_WEB_PID" 2>/dev/null || true
  [ -z "$QA_API_PID" ] || wait "$QA_API_PID" 2>/dev/null || true
  mkdir -p "$ROOT/frontend/test-results/learning-content-browser"
  [ ! -f "$QA_RUNTIME_DIR/api.log" ] || cp "$QA_RUNTIME_DIR/api.log" "$ROOT/frontend/test-results/learning-content-browser/api.log"
  [ ! -f "$QA_RUNTIME_DIR/web.log" ] || cp "$QA_RUNTIME_DIR/web.log" "$ROOT/frontend/test-results/learning-content-browser/web.log"
}
trap cleanup EXIT
(cd backend; uv run --locked alembic -c alembic.ini upgrade head)
# Unit tests intentionally leave their last minimal fixture behind. Reuse the
# guarded test cleanup before seeding a complete browser scenario.
uv run --project backend --locked python - <<'CLEAN_TEST_FIXTURES'
import asyncio
from app.config import Settings
from tests.conftest import clean_test_db

async def main():
    cleanup = clean_test_db.__wrapped__(None, Settings(app_env="test"))
    await anext(cleanup)
    try:
        await anext(cleanup)
    except StopAsyncIteration:
        pass

asyncio.run(main())
CLEAN_TEST_FIXTURES
uv run --project backend --locked python -m app.scripts.prepare_learning_browser_test
uv run --project backend --locked python -m app.scripts.prepare_final_learning_test
backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$QA_API_PORT" > "$QA_RUNTIME_DIR/api.log" 2>&1 &
QA_API_PID=$!
(cd frontend; exec env VITE_API_PROXY_TARGET="$QA_API_URL" node node_modules/vite/bin/vite.js --config vite.config.ts --host 127.0.0.1 --port "$QA_WEB_PORT" --strictPort) > "$QA_RUNTIME_DIR/web.log" 2>&1 &
QA_WEB_PID=$!
for _ in $(seq 1 30); do
  if curl -fsS "$QA_API_URL/health/ready" >/dev/null 2>&1 && curl -fsS "$QA_WEB_URL/login" >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS "$QA_API_URL/health/ready" >/dev/null
curl -fsS "$QA_WEB_URL/login" >/dev/null
cd frontend
HTML_LEARNING_E2E=1 FINAL_LEARNING_E2E=1 CODELAB_E2E_BASE_URL="$QA_WEB_URL" ./node_modules/.bin/playwright test --config playwright.config.ts src/e2e/learning-html.spec.ts src/e2e/original-books.spec.ts src/e2e/ai-fruit-trainer.spec.ts src/e2e/autoplay-examples.spec.ts src/e2e/lookup.spec.ts src/e2e/final-learning-flow.spec.ts "$@"
