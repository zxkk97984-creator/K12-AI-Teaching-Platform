#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
. "$ROOT/scripts/load-runtime-env.sh"

: "${POSTGRES_DEV_PASSWORD:?POSTGRES_DEV_PASSWORD is required}"
: "${POSTGRES_TEST_PASSWORD:?POSTGRES_TEST_PASSWORD is required}"
: "${APP_SESSION_SECRET:?APP_SESSION_SECRET is required}"
export APP_ENV=development
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://k12r1_app:${POSTGRES_DEV_PASSWORD}@127.0.0.1:55433/k12r1_dev}"
export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+asyncpg://k12r1_test:${POSTGRES_TEST_PASSWORD}@127.0.0.1:55434/k12r1_test}"

with_runner=0
for arg in "$@"; do
  case "$arg" in
    --with-runner) with_runner=1 ;;
    -h|--help)
      printf '用法：./k12 dev [--with-runner]\n'
      exit 0
      ;;
    *) printf '未知参数：%s\n' "$arg" >&2; exit 2 ;;
  esac
done
command -v setsid >/dev/null 2>&1 || {
  printf '缺少 setsid，无法安全管理开发服务子进程。\n' >&2
  exit 1
}

api_pid=""
web_pid=""
worker_pid=""
memory_worker_pid=""
runner_pid=""
dev_pid_file=""

cleanup() {
  local pid
  for pid in "$web_pid" "$api_pid" "$worker_pid" "$memory_worker_pid" "$runner_pid"; do
    # npm and uvicorn spawn children. Each service has its own session, so
    # stop the entire service group even if its original parent exited.
    if [ -n "$pid" ]; then
      kill -TERM -- "-$pid" 2>/dev/null || true
    fi
  done
  for pid in "$web_pid" "$api_pid" "$worker_pid" "$memory_worker_pid" "$runner_pid"; do
    if [ -n "$pid" ]; then
      wait "$pid" 2>/dev/null || true
    fi
  done
  if [ -n "$memory_worker_pid" ] && [ -f "$K12_RUNTIME_STATE_DIR/memory-worker.pid" ] \
    && [ "$(cat "$K12_RUNTIME_STATE_DIR/memory-worker.pid")" = "$memory_worker_pid" ]; then
    rm -f -- "$K12_RUNTIME_STATE_DIR/memory-worker.pid"
  fi
  if [ -n "$dev_pid_file" ] && [ -f "$dev_pid_file" ] \
    && [ "$(cat "$dev_pid_file")" = "$$" ]; then
    rm -f -- "$dev_pid_file"
  fi
}
trap cleanup EXIT
trap 'exit 0' INT TERM

# `./k12 stop` may signal this foreground development session. Keep its PID in
# the user state directory and verify the process command line before killing.
mkdir -p "$K12_RUNTIME_STATE_DIR"
chmod 700 "$K12_RUNTIME_STATE_DIR"
dev_pid_file="$K12_RUNTIME_STATE_DIR/dev.pid"
if [ -f "$dev_pid_file" ]; then
  read -r previous_dev_pid < "$dev_pid_file" || true
  if [[ "${previous_dev_pid:-}" =~ ^[0-9]+$ ]] \
    && [ -r "/proc/$previous_dev_pid/cmdline" ] \
    && [[ "$(tr '\0' ' ' < "/proc/$previous_dev_pid/cmdline")" == *"$ROOT/scripts/dev.sh"* ]]; then
    printf '本项目开发服务已运行（PID %s）。\n' "$previous_dev_pid" >&2
    exit 1
  fi
fi
printf '%s\n' "$$" > "$dev_pid_file"

stop_project_service() {
  local service="$1"
  local ids
  ids="$(docker ps --filter "label=com.docker.compose.project=k12r1" \
    --filter "label=com.docker.compose.service=$service" --format '{{.ID}}' 2>/dev/null || true)"
  if [ -n "$ids" ]; then
    printf '停止本项目 Compose %s（保留数据库和数据卷）\n' "$service"
    # The IDs came directly from Docker's compose labels; do not stop any
    # unrelated container sharing a port.
    docker stop --time 10 $ids >/dev/null
  fi
}

port_listeners() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -H -ltnp "sport = :$port" 2>/dev/null || true
  elif command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
  elif command -v fuser >/dev/null 2>&1; then
    fuser -n tcp "$port" 2>/dev/null || true
  else
    printf '无法检查 TCP 端口 %s（需要 ss、lsof 或 fuser）\n' "$port" >&2
    return 2
  fi
}

assert_port_free() {
  local port="$1"
  local listeners
  listeners="$(port_listeners "$port")"
  if [ -n "$listeners" ]; then
    printf '端口 %s 仍被占用，未停止未知进程：\n%s\n' "$port" "$listeners" >&2
    return 1
  fi
}

ensure_runner_token() {
  mkdir -p "$K12_RUNTIME_STATE_DIR"
  chmod 700 "$K12_RUNTIME_STATE_DIR"
  local token_file="${RUNNER_CONTROL_TOKEN_FILE:-$K12_RUNTIME_STATE_DIR/runner-control-token}"
  if [ -z "${RUNNER_CONTROL_TOKEN:-}" ]; then
    if [ -f "$token_file" ]; then
      RUNNER_CONTROL_TOKEN="$(cat "$token_file")"
    else
      if command -v openssl >/dev/null 2>&1; then
        RUNNER_CONTROL_TOKEN="$(openssl rand -hex 32)"
      else
        RUNNER_CONTROL_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
      fi
      temporary_token="$(mktemp "$K12_RUNTIME_STATE_DIR/.runner-token.XXXXXX")"
      chmod 600 "$temporary_token"
      printf '%s\n' "$RUNNER_CONTROL_TOKEN" > "$temporary_token"
      mv -- "$temporary_token" "$token_file"
      chmod 600 "$token_file"
    fi
  fi
  if ! [[ "$RUNNER_CONTROL_TOKEN" =~ ^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$ ]]; then
    printf 'RUNNER_CONTROL_TOKEN has an invalid format.\n' >&2
    return 1
  fi
  export RUNNER_CONTROL_TOKEN
  export CODELAB_RUNNER_TOKEN="${CODELAB_RUNNER_TOKEN:-$RUNNER_CONTROL_TOKEN}"
}

reuse_or_start_runner() {
  local listeners runner_listener runner_pid_candidate runner_args status
  listeners="$(port_listeners "${RUNNER_PORT:-18090}")"
  if [ -n "$listeners" ]; then
    runner_listener="$listeners"
    runner_pid_candidate="$(sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' <<< "$runner_listener" | head -n 1)"
    runner_args="$(ps -p "$runner_pid_candidate" -o args= 2>/dev/null || true)"
    if [[ "$runner_args" == *"runner.host.server"* ]] \
      && curl -fsS --max-time 2 "http://127.0.0.1:${RUNNER_PORT:-18090}/health" >/dev/null; then
      printf '复用已运行的本项目 runner（PID %s）\n' "$runner_pid_candidate"
      return 0
    fi
    printf 'runner 端口 %s 已被未知或未就绪进程占用：\n%s\n' \
      "${RUNNER_PORT:-18090}" "$runner_listener" >&2
    return 1
  fi

  setsid "$ROOT/scripts/codelab-runner-server.sh" &
  runner_pid=$!
  for _ in $(seq 1 30); do
    status="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 2 \
      "http://127.0.0.1:${RUNNER_PORT:-18090}/health" || true)"
    if [ "$status" = "200" ]; then
      printf 'runner 已就绪：http://127.0.0.1:%s（镜像 %s）\n' \
        "${RUNNER_PORT:-18090}" "${RUNNER_IMAGE:-k12-codelab-runner:0.1.0}"
      return 0
    fi
    if ! kill -0 "$runner_pid" 2>/dev/null; then
      printf 'runner 启动失败，请检查 Docker 和镜像 %s。\n' \
        "${RUNNER_IMAGE:-k12-codelab-runner:0.1.0}" >&2
      return 1
    fi
    sleep 1
  done
  printf 'runner 在 30 秒内未就绪。\n' >&2
  return 1
}

# Host mode owns API, worker and web. Stop only containers belonging to this
# Compose project, then fail closed if any unknown process still owns a port.
stop_project_service api
stop_project_service worker
stop_project_service memory-worker
stop_project_service web
for port in 18081 15173; do
  for _ in $(seq 1 15); do
    if [ -z "$(port_listeners "$port")" ]; then
      break
    fi
    sleep 1
  done
  assert_port_free "$port"
done

"$ROOT/scripts/prepare-runtime-storage.sh"

if [ "$with_runner" -eq 1 ]; then
  ensure_runner_token
  export RUNNER_HOST="${RUNNER_HOST:-127.0.0.1}"
  export RUNNER_PORT="${RUNNER_PORT:-18090}"
  export RUNNER_IMAGE="${RUNNER_IMAGE:-k12-codelab-runner:0.1.0}"
  export CODELAB_RUNNER_URL="${CODELAB_RUNNER_URL:-http://127.0.0.1:${RUNNER_PORT}}"
  reuse_or_start_runner
else
  export CODELAB_RUNNER_URL=""
  export CODELAB_RUNNER_TOKEN=""
fi

"$ROOT/scripts/compose.sh" up -d postgres-dev postgres-test
(
  cd backend
  uv run --locked alembic -c alembic.ini upgrade head
)

setsid uv run --project backend --locked uvicorn app.main:app --host 127.0.0.1 --port 18081 --reload &
api_pid=$!
setsid npm run dev --prefix frontend &
web_pid=$!
if [ "$with_runner" -eq 1 ]; then
  setsid uv run --project backend --locked python -m app.jobs.worker &
  worker_pid=$!
fi

setsid uv run --project backend --locked python -m app.jobs.memory_worker &
memory_worker_pid=$!
printf '%s\n' "$memory_worker_pid" > "$K12_RUNTIME_STATE_DIR/memory-worker.pid"

for _ in $(seq 1 45); do
  if curl -fsS --max-time 2 http://127.0.0.1:18081/health/ready >/dev/null \
    && curl -fsS --max-time 2 http://127.0.0.1:15173/ >/dev/null; then
    printf 'K12 host runtime 已就绪：前端 http://127.0.0.1:15173，API http://127.0.0.1:18081\n'
    wait
    exit $?
  fi
  if ! kill -0 "$api_pid" 2>/dev/null; then
    printf 'API 进程提前退出。\n' >&2
    exit 1
  fi
  sleep 1
done
printf 'API 或前端在 45 秒内未就绪，请查看上方日志。\n' >&2
exit 1
