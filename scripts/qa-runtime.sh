#!/usr/bin/env bash
# Source after load-runtime-env.sh: all QA URLs/storage derive from the selected file.
export QA_WEB_PORT="${QA_WEB_PORT:-15174}" QA_API_PORT="${QA_API_PORT:-18082}"
for k12_qa_port in "$QA_WEB_PORT" "$QA_API_PORT"; do
  if ! [[ "$k12_qa_port" =~ ^[0-9]+$ ]] || (( k12_qa_port < 1024 || k12_qa_port > 65535 )); then
    printf 'QA ports must be integers between 1024 and 65535\n' >&2
    return 1 2>/dev/null || exit 1
  fi
done
if [ "$QA_WEB_PORT" = "$QA_API_PORT" ]; then
  printf 'QA Web and API ports must differ\n' >&2
  return 1 2>/dev/null || exit 1
fi
export QA_RUNTIME_DIR="${QA_RUNTIME_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/k12/learning-browser-runtime}"
case "$QA_RUNTIME_DIR" in /*) ;; *) printf 'QA_RUNTIME_DIR must be absolute\n' >&2; return 1 2>/dev/null || exit 1 ;; esac
export QA_WEB_URL="http://127.0.0.1:$QA_WEB_PORT" QA_API_URL="http://127.0.0.1:$QA_API_PORT"
# localhost remains explicit for older single-machine callers. The browser uses 127.0.0.1.
export ALLOWED_ORIGINS="$QA_WEB_URL,http://localhost:$QA_WEB_PORT"
# Agent storage must stay in its assigned persistent root. Legacy QA uses its cache.
if [ "${QA_ISOLATED:-0}" != 1 ]; then
  export RESOURCE_STORAGE_ROOT="$QA_RUNTIME_DIR/resources"
  export AUTHORING_ARTIFACT_ROOT="$QA_RUNTIME_DIR/authoring"
  export AUTHORING_BUNDLE_ROOT="$QA_RUNTIME_DIR/authoring-bundles"
  export KNODO_BUDGET_LEDGER_PATH="$QA_RUNTIME_DIR/private/knodo-runtime-budget.json"
fi
export TMPDIR="$QA_RUNTIME_DIR/tmp"
install -d -m 700 "$TMPDIR"
unset k12_qa_port
