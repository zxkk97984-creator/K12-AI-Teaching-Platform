#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${RUNNER_IMAGE:-k12-codelab-runner:0.1.0}"
cd "$ROOT"

docker build --pull=false --file runner/Dockerfile --tag "$IMAGE" runner
docker image inspect "$IMAGE" --format 'runner image={{index .RepoTags 0}} id={{.Id}}'
