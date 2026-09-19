from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta

import pytest
from runner.host.runner import DEFAULT_IMAGE, DockerRunner, RunRequest


def _docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    daemon = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], check=False)
    image = subprocess.run(
        ["docker", "image", "inspect", os.getenv("RUNNER_IMAGE", DEFAULT_IMAGE)], check=False
    )
    return daemon.returncode == 0 and image.returncode == 0


if not _docker_ready():
    pytest.skip("T24 live tests require Docker and the built runner image", allow_module_level=True)


def _request(code: str, *, case_id: str, input_value: dict) -> RunRequest:
    return RunRequest.from_payload(
        {
            "case_id": case_id,
            "task_id": "temperature-converter",
            "task_revision": 1,
            "entrypoint": "celsius_to_fahrenheit",
            "input": input_value,
            "student_code": code,
            "owner_id": "t24-live-owner",
            "lease_id": case_id,
        }
    )


@pytest.fixture
def runner() -> DockerRunner:
    return DockerRunner(image=os.getenv("RUNNER_IMAGE", DEFAULT_IMAGE))


def test_real_container_correct_json_and_student_stdout_are_separate(
    runner: DockerRunner,
) -> None:
    result = runner.run_case(
        _request(
            "def celsius_to_fahrenheit(celsius):\n"
            "    print('student trace')\n"
            "    return celsius * 9 / 5 + 32\n",
            case_id="correct",
            input_value={"celsius": 0},
        )
    )
    assert result.execution_status == "COMPLETED"
    assert result.actual_output == 32
    assert result.student_stdout == "student trace\n"
    assert result.code_sha256


def test_real_container_syntax_and_readonly_failures_are_not_success(
    runner: DockerRunner,
) -> None:
    syntax = runner.run_case(
        _request(
            "def celsius_to_fahrenheit(celsius)\n    return 32\n",
            case_id="syntax",
            input_value={"celsius": 0},
        )
    )
    readonly = runner.run_case(
        _request(
            "def celsius_to_fahrenheit(celsius):\n    open('/etc/t24-write', 'w')\n    return 32\n",
            case_id="readonly",
            input_value={"celsius": 0},
        )
    )
    assert syntax.execution_status == "STUDENT_EXCEPTION"
    assert readonly.execution_status == "STUDENT_EXCEPTION"


def test_real_container_network_and_timeout_are_bounded(runner: DockerRunner) -> None:
    network = runner.run_case(
        _request(
            "def celsius_to_fahrenheit(celsius):\n"
            "    import socket\n"
            "    socket.create_connection(('1.1.1.1', 53), 0.2)\n"
            "    return 32\n",
            case_id="network",
            input_value={"celsius": 0},
        )
    )
    timeout = runner.run_case(
        _request(
            "def celsius_to_fahrenheit(celsius):\n    while True:\n        pass\n",
            case_id="timeout",
            input_value={"celsius": 0},
        )
    )
    assert network.execution_status == "STUDENT_EXCEPTION"
    assert timeout.execution_status == "TIMEOUT"
    assert timeout.elapsed_ms < 10_000


def test_real_container_output_is_limited_during_read(runner: DockerRunner) -> None:
    result = runner.run_case(
        _request(
            "def celsius_to_fahrenheit(celsius):\n    while True:\n        print('x' * 4096)\n",
            case_id="flood",
            input_value={"celsius": 0},
        )
    )
    assert result.execution_status == "OUTPUT_LIMIT"
    assert result.stdout_bytes <= runner.limits.max_output_bytes


def test_cleanup_only_removes_owned_stopped_expired_containers(runner: DockerRunner) -> None:
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    image = os.getenv("RUNNER_IMAGE", DEFAULT_IMAGE)
    base = [
        "docker",
        "run",
        "-d",
        "--entrypoint",
        "python",
        "--label",
        "com.k12.runner.project=k12-codelab",
        "--label",
        "com.k12.runner.owner_id=t24-live-owner",
        "--label",
        f"com.k12.runner.lease_expires_at={past}",
        image,
    ]
    stopped = (
        subprocess.run([*base, "-c", "pass"], check=True, stdout=subprocess.PIPE)
        .stdout.decode()
        .strip()
    )
    active = (
        subprocess.run(
            [*base, "-c", "import time; time.sleep(60)"],
            check=True,
            stdout=subprocess.PIPE,
        )
        .stdout.decode()
        .strip()
    )
    other = (
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--entrypoint",
                "python",
                "--label",
                "com.k12.runner.project=old-project",
                "--label",
                "com.k12.runner.owner_id=t24-live-owner",
                "--label",
                f"com.k12.runner.lease_expires_at={past}",
                image,
                "-c",
                "pass",
            ],
            check=True,
            stdout=subprocess.PIPE,
        )
        .stdout.decode()
        .strip()
    )
    try:
        removed = runner.cleanup_expired("t24-live-owner")
        assert any(stopped.startswith(container_id) for container_id in removed)
        assert subprocess.run(["docker", "inspect", stopped], check=False).returncode != 0
        assert subprocess.run(["docker", "inspect", active], check=False).returncode == 0
        assert subprocess.run(["docker", "inspect", other], check=False).returncode == 0
    finally:
        subprocess.run(
            ["docker", "rm", "-f", active, other], check=False, stdout=subprocess.DEVNULL
        )
