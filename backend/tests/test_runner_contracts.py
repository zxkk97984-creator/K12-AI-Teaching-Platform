from __future__ import annotations

import pytest
from runner.host.runner import DockerRunner, InvalidRunRequest, RunnerUnavailable, RunRequest


def _payload(**overrides):
    payload = {
        "case_id": "unit-case",
        "task_id": "temperature-converter",
        "task_revision": 1,
        "entrypoint": "celsius_to_fahrenheit",
        "input": {"celsius": 0},
        "student_code": "def celsius_to_fahrenheit(celsius):\n    return celsius\n",
        "owner_id": "unit-owner",
        "lease_id": "unit-lease",
    }
    payload.update(overrides)
    return payload


def test_request_rejects_user_selected_image_volume_and_command() -> None:
    for field in ("image", "volume", "command"):
        payload = _payload(**{field: "attacker-controlled"})
        with pytest.raises(InvalidRunRequest, match="unsupported"):
            RunRequest.from_payload(payload)


def test_request_authorizes_task_revision_and_calculates_code_hash() -> None:
    request = RunRequest.from_payload(_payload())
    assert len(request.code_sha256) == 64
    with pytest.raises(InvalidRunRequest, match="not authorized"):
        RunRequest.from_payload(_payload(task_revision=2))
    with pytest.raises(InvalidRunRequest, match="not authorized"):
        RunRequest.from_payload(_payload(task_id="unknown-task"))


def test_missing_docker_fails_closed_without_host_execution() -> None:
    with pytest.raises(RunnerUnavailable, match="fallback is disabled"):
        DockerRunner(docker_bin="k12-docker-command-that-does-not-exist").ensure_available()


def test_missing_fixed_image_fails_closed_without_host_execution() -> None:
    with pytest.raises(RunnerUnavailable, match="fixed runner image"):
        DockerRunner(image="k12-image-that-does-not-exist:0.0.0").ensure_available()
