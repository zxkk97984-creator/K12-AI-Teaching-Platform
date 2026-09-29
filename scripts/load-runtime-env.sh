#!/usr/bin/env bash
# Source the persistent, user-owned local runtime configuration without eval.
# This file is intended to be sourced by project scripts.

k12_account_home="$(getent passwd "$(id -u)" | cut -d: -f6)"
if [ -z "$k12_account_home" ]; then
  printf 'cannot resolve the current account home directory\n' >&2
  return 1 2>/dev/null || exit 1
fi

export K12_RUNTIME_ENV_FILE="${K12_RUNTIME_ENV_FILE:-${XDG_CONFIG_HOME:-$k12_account_home/.config}/k12/runtime.env}"

if [ ! -f "$K12_RUNTIME_ENV_FILE" ]; then
  printf 'K12 runtime config is missing: %s\nRun ./k12 setup first.\n' \
    "$K12_RUNTIME_ENV_FILE" >&2
  return 1 2>/dev/null || exit 1
fi

k12_runtime_mode="$(stat -c '%a' "$K12_RUNTIME_ENV_FILE")"
if (( (8#$k12_runtime_mode & 077) != 0 )); then
  printf 'K12 runtime config must not be readable by group/others: %s (mode %s)\n' \
    "$K12_RUNTIME_ENV_FILE" "$k12_runtime_mode" >&2
  return 1 2>/dev/null || exit 1
fi

while IFS= read -r k12_runtime_line || [ -n "$k12_runtime_line" ]; do
  case "$k12_runtime_line" in
    ''|'#'*) continue ;;
  esac
  k12_runtime_name="${k12_runtime_line%%=*}"
  k12_runtime_value="${k12_runtime_line#*=}"
  if [ "$k12_runtime_name" = "$k12_runtime_line" ] \
    || ! [[ "$k12_runtime_name" =~ ^[A-Z][A-Z0-9_]*$ ]]; then
    printf 'invalid entry in K12 runtime config: %s\n' "$k12_runtime_name" >&2
    return 1 2>/dev/null || exit 1
  fi
  export "$k12_runtime_name=$k12_runtime_value"
done < "$K12_RUNTIME_ENV_FILE"

# Host processes and Compose share one absolute application-storage root. Keep
# this outside the repository so uploads, authoring artefacts and the Knodo
# budget ledger cannot be mistaken for source files or committed by accident.
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/runtime-storage.sh"

if [ -n "${POSTGRES_DEV_PASSWORD:-}" ]; then
  export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://k12r1_app:${POSTGRES_DEV_PASSWORD}@127.0.0.1:55433/k12r1_dev}"
fi
if [ -n "${POSTGRES_TEST_PASSWORD:-}" ]; then
  export TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+asyncpg://k12r1_test:${POSTGRES_TEST_PASSWORD}@127.0.0.1:55434/k12r1_test}"
fi

unset k12_account_home k12_runtime_line k12_runtime_mode k12_runtime_name k12_runtime_value
