#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
. "$ROOT/scripts/runtime-storage.sh"

volume_name="${K12_COMPOSE_STORAGE_VOLUME:-k12r1-app-storage}"
source_image="${K12_STORAGE_COPY_IMAGE:-alpine:3.20}"

usage() {
  cat <<'EOF'
用法：
  ./scripts/prepare-runtime-storage.sh

初始化或核对宿主机与 Compose 共用的运行时存储目录。目标已有文件且与
Compose 数据卷不同会直接失败，脚本不会覆盖预算账本、上传文件或产物。
EOF
}

for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    *) printf '未知参数：%s\n' "$arg" >&2; usage >&2; exit 2 ;;
  esac
done

mkdir -p "$K12_RUNTIME_STORAGE_ROOT"
chmod 700 "$K12_RUNTIME_STORAGE_ROOT"

# A current or stopped K12 API/worker container may already use this exact
# host directory. In that case the older named volume is historical, and
# comparing it to the active store would report a false conflict.
bind_container_count=0
all_app_containers_use_bind=1
for service in api worker; do
  container_ids="$(docker ps -aq --filter 'label=com.docker.compose.project=k12r1' \
    --filter "label=com.docker.compose.service=$service" 2>/dev/null || true)"
  for container_id in $container_ids; do
    mount_source="$(docker inspect "$container_id" \
      --format '{{range .Mounts}}{{if eq .Destination "/app/backend/storage"}}{{.Source}}{{end}}{{end}}' 2>/dev/null || true)"
    if [ "$mount_source" = "$K12_RUNTIME_STORAGE_ROOT" ]; then
      bind_container_count=$((bind_container_count + 1))
    else
      all_app_containers_use_bind=0
    fi
  done
done
if [ "$bind_container_count" -gt 0 ] && [ "$all_app_containers_use_bind" -eq 1 ]; then
  mkdir -p "$K12_RUNTIME_STORAGE_ROOT/private" \
    "$K12_RUNTIME_STORAGE_ROOT/resources" \
    "$K12_RUNTIME_STORAGE_ROOT/authoring" \
    "$K12_RUNTIME_STORAGE_ROOT/authoring-bundles"
  chmod 700 "$K12_RUNTIME_STORAGE_ROOT/private"
  printf 'Runtime storage already bound to this project: %s\n' "$K12_RUNTIME_STORAGE_ROOT"
  exit 0
fi

if ! docker volume inspect "$volume_name" >/dev/null 2>&1; then
  mkdir -p "$K12_RUNTIME_STORAGE_ROOT/private" \
    "$K12_RUNTIME_STORAGE_ROOT/resources" \
    "$K12_RUNTIME_STORAGE_ROOT/authoring" \
    "$K12_RUNTIME_STORAGE_ROOT/authoring-bundles"
  chmod 700 "$K12_RUNTIME_STORAGE_ROOT/private"
  printf 'Initialized runtime storage: %s\n' "$K12_RUNTIME_STORAGE_ROOT"
  exit 0
fi

running_services=()
for service in api worker web; do
  container_ids="$(docker ps --filter "label=com.docker.compose.project=k12r1" \
    --filter "label=com.docker.compose.service=$service" --format '{{.ID}}' 2>/dev/null || true)"
  if [ -n "$container_ids" ]; then
    running_services+=("$service")
  fi
done
if [ "${#running_services[@]}" -gt 0 ]; then
  printf 'Cannot copy Compose storage while services are running: %s\n' \
    "${running_services[*]}" >&2
  printf 'Stop only this project API/worker/web first, then retry. Databases stay running.\n' >&2
  exit 3
fi

stage="$(mktemp -d "${TMPDIR:-/tmp}/k12-runtime-storage.XXXXXX")"
cleanup() { rm -rf -- "$stage"; }
trap cleanup EXIT

# Extract as the invoking user. A root-owned Docker volume must not leave a
# host-mode process unable to update its own budget or uploaded files.
docker run --rm \
  -v "$volume_name:/source:ro" \
  "$source_image" sh -c 'tar -C /source -cf - .' \
  | tar -C "$stage" -xf -

# The repository-local ``storage/private`` file belongs to the old container
# runtime and is deliberately not treated as a second live ledger.  The
# Compose volume is the authoritative store used by the running API/worker;
# keeping this legacy file untouched avoids both accidental overwrite and a
# false conflict when switching to host mode.

has_target_files=0
if find "$K12_RUNTIME_STORAGE_ROOT" -mindepth 1 -print -quit | grep -q .; then
  has_target_files=1
fi

if [ "$has_target_files" -eq 1 ]; then
  if ! diff -qr --exclude='.*.lock' "$stage" "$K12_RUNTIME_STORAGE_ROOT" >/dev/null; then
    printf 'Runtime storage conflict detected; no files were changed.\n' >&2
    printf 'Compose volume: %s\nHost target: %s\n' "$volume_name" "$K12_RUNTIME_STORAGE_ROOT" >&2
    diff -qr --exclude='.*.lock' "$stage" "$K12_RUNTIME_STORAGE_ROOT" | head -80 >&2 || true
    printf 'Resolve the conflict explicitly before switching runtime modes.\n' >&2
    exit 4
  fi
else
  tar -C "$stage" -cf - . | tar -C "$K12_RUNTIME_STORAGE_ROOT" -xf -
fi

mkdir -p "$K12_RUNTIME_STORAGE_ROOT/private" \
  "$K12_RUNTIME_STORAGE_ROOT/resources" \
  "$K12_RUNTIME_STORAGE_ROOT/authoring" \
  "$K12_RUNTIME_STORAGE_ROOT/authoring-bundles"
chmod 700 "$K12_RUNTIME_STORAGE_ROOT/private"
find "$K12_RUNTIME_STORAGE_ROOT/private" -type f -exec chmod go-rwx {} +
printf 'Runtime storage ready: %s (Compose volume %s)\n' \
  "$K12_RUNTIME_STORAGE_ROOT" "$volume_name"
