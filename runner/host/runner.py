from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_LABEL = "com.k12.runner.project"
RUN_LABEL = "com.k12.runner.run_id"
OWNER_LABEL = "com.k12.runner.owner_id"
LEASE_LABEL = "com.k12.runner.lease_expires_at"
INSTANCE_LABEL = "com.k12.runner.instance_id"
PROJECT_ID = "k12-codelab"
DEFAULT_IMAGE = "k12-codelab-runner:0.1.0"
TASK_REVISIONS = {
    "temperature-converter": 1,
    "list-summary": 1,
    "binary-search": 1,
    "odd-even": 1,
    "even-sum": 1,
    "palindrome-check": 1,
    "word-frequency": 1,
    "prediction-accuracy": 1,
    "sort-unique": 1,
    "balanced-brackets": 1,
    "range-sum": 1,
    "climbing-stairs": 1,
}
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
ENTRYPOINT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


class RunnerUnavailable(RuntimeError):
    """Docker or the fixed runner image is unavailable; never use a host fallback."""


class InvalidRunRequest(ValueError):
    pass


@dataclass(frozen=True)
class RunLimits:
    timeout_seconds: float = 3.0
    max_output_bytes: int = 16 * 1024
    memory_bytes: int = 128 * 1024 * 1024
    pids_limit: int = 64
    cpus: float = 0.5
    tmpfs_bytes: int = 8 * 1024 * 1024

    def __post_init__(self) -> None:
        if not 0.1 <= self.timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be between 0.1 and 30")
        if not 1024 <= self.max_output_bytes <= 1024 * 1024:
            raise ValueError("max_output_bytes is outside the runner limit")
        if not 16 * 1024 * 1024 <= self.memory_bytes <= 512 * 1024 * 1024:
            raise ValueError("memory_bytes is outside the runner limit")
        if not 16 <= self.pids_limit <= 256:
            raise ValueError("pids_limit is outside the runner limit")
        if not 0.1 <= self.cpus <= 2:
            raise ValueError("cpus is outside the runner limit")
        if not 1024 * 1024 <= self.tmpfs_bytes <= 64 * 1024 * 1024:
            raise ValueError("tmpfs_bytes is outside the runner limit")


@dataclass(frozen=True)
class RunRequest:
    case_id: str
    task_id: str
    task_revision: int
    entrypoint: str
    input_value: dict[str, Any]
    student_code: str
    owner_id: str
    lease_id: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RunRequest:
        allowed = {
            "case_id",
            "task_id",
            "task_revision",
            "entrypoint",
            "input",
            "student_code",
            "owner_id",
            "lease_id",
        }
        unknown = set(payload) - allowed
        if unknown or set(payload) != allowed:
            raise InvalidRunRequest(
                "request contains an unsupported image, volume, command, or field"
            )
        strings = (
            "case_id",
            "task_id",
            "entrypoint",
            "student_code",
            "owner_id",
            "lease_id",
        )
        if any(not isinstance(payload[key], str) for key in strings):
            raise InvalidRunRequest("request identity and code fields must be strings")
        for key in ("case_id", "task_id", "owner_id", "lease_id"):
            if not TOKEN_RE.fullmatch(payload[key]):
                raise InvalidRunRequest(f"invalid {key}")
        if not ENTRYPOINT_RE.fullmatch(payload["entrypoint"]):
            raise InvalidRunRequest("invalid entrypoint")
        if payload["task_id"] not in TASK_REVISIONS:
            raise InvalidRunRequest("task is not authorized by the runner")
        if payload["task_revision"] != TASK_REVISIONS[payload["task_id"]]:
            raise InvalidRunRequest("task revision is not authorized by the runner")
        if not isinstance(payload["input"], dict):
            raise InvalidRunRequest("input must be a JSON object")
        if len(payload["student_code"].encode("utf-8")) > 64 * 1024:
            raise InvalidRunRequest("student code is too large")
        if "\x00" in payload["student_code"]:
            raise InvalidRunRequest("student code contains a NUL byte")
        try:
            json.dumps(payload["input"], ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError, OverflowError) as exc:
            raise InvalidRunRequest("input is not finite JSON") from exc
        return cls(
            case_id=payload["case_id"],
            task_id=payload["task_id"],
            task_revision=payload["task_revision"],
            entrypoint=payload["entrypoint"],
            input_value=payload["input"],
            student_code=payload["student_code"],
            owner_id=payload["owner_id"],
            lease_id=payload["lease_id"],
        )

    @property
    def code_sha256(self) -> str:
        return hashlib.sha256(self.student_code.encode("utf-8")).hexdigest()

    @property
    def container_name(self) -> str:
        return f"k12-codelab-{self.run_id_token}"

    @property
    def run_id_token(self) -> str:
        return f"{self.owner_id}-{self.lease_id}"


@dataclass(frozen=True)
class ContainerResult:
    case_id: str
    execution_status: str
    actual_output: Any = None
    student_stdout: str = ""
    student_stderr: str = ""
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    exit_code: int | None = None
    elapsed_ms: int = 0
    code_sha256: str = ""
    system_error: str | None = None

    def as_observation(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "case_id": self.case_id,
            "execution_status": self.execution_status,
            "stdout": self.student_stdout,
            "stderr": self.student_stderr,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
        }
        if self.execution_status == "COMPLETED":
            result["actual_output"] = self.actual_output
        return result


@dataclass
class _CollectedProcess:
    stdout: bytes
    stderr: bytes
    output_limited: bool
    timed_out: bool
    exit_code: int | None


def _read_process(
    proc: subprocess.Popen[bytes], max_bytes: int, timeout: float
) -> _CollectedProcess:
    selector = selectors.DefaultSelector()
    buffers: dict[int, bytearray] = {}
    active: set[int] = set()
    stdout_fd = proc.stdout.fileno() if proc.stdout is not None else None
    stderr_fd = proc.stderr.fileno() if proc.stderr is not None else None
    for stream in (proc.stdout, proc.stderr):
        if stream is not None:
            selector.register(stream, selectors.EVENT_READ)
            buffers[stream.fileno()] = bytearray()
            active.add(stream.fileno())
    output_limited = False
    timed_out = False
    deadline = time.monotonic() + timeout
    try:
        while active:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                proc.terminate()
                break
            for key, _ in selector.select(min(0.1, remaining)):
                fd = key.fileobj.fileno()
                chunk = os.read(fd, 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    active.discard(fd)
                    continue
                buffer = buffers[fd]
                if len(buffer) + len(chunk) > max_bytes:
                    remaining_bytes = max(0, max_bytes - len(buffer))
                    buffer.extend(chunk[:remaining_bytes])
                    output_limited = True
                    proc.terminate()
                    break
                buffer.extend(chunk)
            if output_limited:
                break
        try:
            proc.wait(timeout=1.0 if (timed_out or output_limited) else 0.5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=1.0)
    finally:
        selector.close()
        if proc.stdout is not None:
            proc.stdout.close()
        if proc.stderr is not None:
            proc.stderr.close()
    stdout = bytes(buffers.get(stdout_fd, b"")) if stdout_fd is not None else b""
    stderr = bytes(buffers.get(stderr_fd, b"")) if stderr_fd is not None else b""
    return _CollectedProcess(stdout, stderr, output_limited, timed_out, proc.returncode)


class DockerRunner:
    """Launch only the fixed runner image; it never executes student code on the host."""

    def __init__(
        self,
        *,
        image: str = DEFAULT_IMAGE,
        docker_bin: str = "docker",
        project_id: str = PROJECT_ID,
        lease_seconds: int = 60,
        limits: RunLimits | None = None,
    ) -> None:
        if not TOKEN_RE.fullmatch(project_id):
            raise ValueError("invalid runner project id")
        if not 10 <= lease_seconds <= 3600:
            raise ValueError("lease_seconds is outside the runner limit")
        self.image = image
        self.docker_bin = docker_bin
        self.project_id = project_id
        self.lease_seconds = lease_seconds
        self.limits = limits or RunLimits()

    def _docker(
        self, args: list[str], *, timeout: float = 10
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [self.docker_bin, *args],
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def ensure_available(self) -> None:
        if shutil.which(self.docker_bin) is None:
            raise RunnerUnavailable(
                "docker CLI is unavailable; host execution fallback is disabled"
            )
        version = self._docker(["version", "--format", "{{.Server.Version}}"])
        if version.returncode != 0:
            raise RunnerUnavailable(
                "Docker daemon is unavailable; host execution fallback is disabled"
            )
        image = self._docker(["image", "inspect", self.image])
        if image.returncode != 0:
            raise RunnerUnavailable(f"fixed runner image is unavailable: {self.image}")

    def run_case(self, request: RunRequest) -> ContainerResult:
        self.ensure_available()
        started = time.monotonic()
        lease_expires = datetime.now(UTC) + timedelta(seconds=self.lease_seconds)
        instance_id = uuid.uuid4().hex
        container_name = f"k12-codelab-{instance_id}"
        labels = {
            PROJECT_LABEL: self.project_id,
            RUN_LABEL: request.case_id,
            OWNER_LABEL: request.owner_id,
            LEASE_LABEL: lease_expires.isoformat(),
            INSTANCE_LABEL: instance_id,
        }
        with tempfile.TemporaryDirectory(prefix="k12-codelab-run-") as directory:
            root = Path(directory)
            request_path = root / "request.json"
            code_path = root / "student.py"
            request_path.write_text(
                json.dumps(
                    {
                        "case_id": request.case_id,
                        "task_id": request.task_id,
                        "task_revision": request.task_revision,
                        "entrypoint": request.entrypoint,
                        "input": request.input_value,
                    },
                    ensure_ascii=False,
                    allow_nan=False,
                ),
                encoding="utf-8",
            )
            code_path.write_text(request.student_code, encoding="utf-8")
            command = [self.docker_bin, "run", "--rm", "--name", container_name]
            for key, value in labels.items():
                command.extend(["--label", f"{key}={value}"])
            command.extend(
                [
                    "--network",
                    "none",
                    "--read-only",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges:true",
                    "--pids-limit",
                    str(self.limits.pids_limit),
                    "--memory",
                    str(self.limits.memory_bytes),
                    "--memory-swap",
                    str(self.limits.memory_bytes),
                    "--cpus",
                    str(self.limits.cpus),
                    "--tmpfs",
                    f"/tmp:rw,noexec,nosuid,nodev,size={self.limits.tmpfs_bytes}",
                    "--user",
                    "65532:65532",
                    "--env",
                    "PYTHONHASHSEED=0",
                    "--env",
                    "PYTHONDONTWRITEBYTECODE=1",
                    "--mount",
                    f"type=bind,source={request_path},target=/runner/request.json,readonly",
                    "--mount",
                    f"type=bind,source={code_path},target=/runner/student.py,readonly",
                    self.image,
                ]
            )
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env={"PATH": os.environ.get("PATH", "")},
                )
                collected = _read_process(
                    process, self.limits.max_output_bytes, self.limits.timeout_seconds
                )
            except FileNotFoundError as exc:
                raise RunnerUnavailable(
                    "docker CLI disappeared; no host fallback"
                ) from exc
            elapsed_ms = int((time.monotonic() - started) * 1000)
            if collected.timed_out:
                self._remove_exact_container(container_name)
                return ContainerResult(
                    request.case_id,
                    "TIMEOUT",
                    exit_code=collected.exit_code,
                    elapsed_ms=elapsed_ms,
                    code_sha256=request.code_sha256,
                )
            if collected.output_limited:
                self._remove_exact_container(container_name)
                return ContainerResult(
                    request.case_id,
                    "OUTPUT_LIMIT",
                    stdout_bytes=len(collected.stdout),
                    stderr_bytes=len(collected.stderr),
                    exit_code=collected.exit_code,
                    elapsed_ms=elapsed_ms,
                    code_sha256=request.code_sha256,
                )
            payload = self._parse_result(collected.stdout)
            if payload is None or payload.get("case_id") != request.case_id:
                return ContainerResult(
                    request.case_id,
                    "SYSTEM_ERROR",
                    stdout_bytes=len(collected.stdout),
                    stderr_bytes=len(collected.stderr),
                    exit_code=collected.exit_code,
                    elapsed_ms=elapsed_ms,
                    code_sha256=request.code_sha256,
                    system_error="runner protocol did not return a JSON observation",
                )
            return ContainerResult(
                request.case_id,
                str(payload.get("execution_status", "SYSTEM_ERROR")),
                actual_output=payload.get("actual_output"),
                student_stdout=str(payload.get("stdout", "")),
                student_stderr=str(payload.get("stderr", "")),
                stdout_bytes=int(payload.get("stdout_bytes", 0)),
                stderr_bytes=int(payload.get("stderr_bytes", 0)),
                exit_code=collected.exit_code,
                elapsed_ms=elapsed_ms,
                code_sha256=request.code_sha256,
                system_error=payload.get("error_type"),
            )

    def _parse_result(self, stdout: bytes) -> dict[str, Any] | None:
        for line in reversed(stdout.decode("utf-8", errors="replace").splitlines()):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(value, dict)
                and value.get("schema_version") == "k12.runner.observation.v1"
            ):
                return value
        return None

    def _remove_exact_container(self, name: str) -> None:
        self._docker(["rm", "-f", name], timeout=5)

    def cleanup_expired(
        self, owner_id: str, *, now: datetime | None = None
    ) -> list[str]:
        if not TOKEN_RE.fullmatch(owner_id):
            raise ValueError("invalid owner_id")
        self.ensure_available()
        moment = now or datetime.now(UTC)
        listing = self._docker(
            [
                "ps",
                "-aq",
                "--filter",
                f"label={PROJECT_LABEL}={self.project_id}",
                "--filter",
                f"label={OWNER_LABEL}={owner_id}",
            ]
        )
        if listing.returncode != 0:
            raise RunnerUnavailable("could not inspect owned runner containers")
        removed: list[str] = []
        for container_id in listing.stdout.decode().splitlines():
            inspected = self._docker(["inspect", container_id], timeout=5)
            if inspected.returncode != 0:
                continue
            try:
                record = json.loads(inspected.stdout)[0]
                state = record.get("State") or {}
                labels = (record.get("Config") or {}).get("Labels") or {}
                lease = datetime.fromisoformat(labels[LEASE_LABEL])
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if state.get("Running") or lease > moment:
                continue
            if (
                labels.get(PROJECT_LABEL) != self.project_id
                or labels.get(OWNER_LABEL) != owner_id
            ):
                continue
            deleted = self._docker(["rm", container_id], timeout=5)
            if deleted.returncode == 0:
                removed.append(container_id)
        return removed
