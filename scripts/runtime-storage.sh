#!/usr/bin/env bash
# Shared local storage helpers for host and Compose runtime modes.
#
# The application volume used by Compose and the host-run API/worker must
# resolve the same files. Keep this helper free of secrets and make every
# path absolute so a changed working directory cannot select another store.

if [ -z "${K12_RUNTIME_STORAGE_ROOT:-}" ]; then
  k12_storage_home="${XDG_DATA_HOME:-${HOME:-/tmp}/.local/share}"
  export K12_RUNTIME_STORAGE_ROOT="$k12_storage_home/k12/runtime-storage"
  unset k12_storage_home
fi

if [ -z "${K12_RUNTIME_STATE_DIR:-}" ]; then
  k12_state_home="${XDG_STATE_HOME:-${HOME:-/tmp}/.local/state}"
  export K12_RUNTIME_STATE_DIR="$k12_state_home/k12"
  unset k12_state_home
fi

case "$K12_RUNTIME_STORAGE_ROOT" in
  /*) ;;
  *)
    printf 'K12_RUNTIME_STORAGE_ROOT must be an absolute path: %s\n' \
      "$K12_RUNTIME_STORAGE_ROOT" >&2
    return 1 2>/dev/null || exit 1
    ;;
esac

case "$K12_RUNTIME_STATE_DIR" in
  /*) ;;
  *)
    printf 'K12_RUNTIME_STATE_DIR must be an absolute path: %s\n' \
      "$K12_RUNTIME_STATE_DIR" >&2
    return 1 2>/dev/null || exit 1
    ;;
esac

# These are the host equivalents of the paths mounted at /app/backend/storage
# in Compose. Compose sets the container paths explicitly in compose.yaml.
if [ "${K12_RUNTIME_CONTAINER:-0}" != "1" ]; then
  export RESOURCE_STORAGE_ROOT="$K12_RUNTIME_STORAGE_ROOT/resources"
  export AUTHORING_ARTIFACT_ROOT="$K12_RUNTIME_STORAGE_ROOT/authoring"
  export AUTHORING_BUNDLE_ROOT="$K12_RUNTIME_STORAGE_ROOT/authoring-bundles"
  export KNODO_BUDGET_LEDGER_PATH="$K12_RUNTIME_STORAGE_ROOT/private/knodo-runtime-budget.json"
fi
