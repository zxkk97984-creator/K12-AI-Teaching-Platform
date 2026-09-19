"""Run exactly one authorized function-json case inside the restricted image.

The host launcher mounts only this case's input and the student's source. The
worker never receives the trusted oracle, hidden case list, application
session, Docker client configuration, or Knodo credentials.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

REQUEST_PATH = Path("/runner/request.json")
CODE_PATH = Path("/runner/student.py")
MAX_CASE_ID_LENGTH = 96
ENTRYPOINT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


class OutputLimitExceeded(RuntimeError):
    pass


class LimitedTextIO(io.TextIOBase):
    """Bound captured student output before it can consume container memory."""

    def __init__(self, limit: int) -> None:
        super().__init__()
        self.limit = limit
        self._size = 0
        self._chunks: list[str] = []

    @property
    def size(self) -> int:
        return self._size

    def write(self, value: str) -> int:
        if not isinstance(value, str):
            value = str(value)
        encoded = value.encode("utf-8", errors="replace")
        if self._size + len(encoded) > self.limit:
            remaining = max(0, self.limit - self._size)
            if remaining:
                self._chunks.append(
                    encoded[:remaining].decode("utf-8", errors="replace")
                )
                self._size += remaining
            raise OutputLimitExceeded("student output limit exceeded")
        self._chunks.append(value)
        self._size += len(encoded)
        return len(value)

    def getvalue(self) -> str:
        return "".join(self._chunks)

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        return False


def _error_result(
    request: dict[str, Any], status: str, error_type: str
) -> dict[str, Any]:
    return {
        "schema_version": "k12.runner.observation.v1",
        "case_id": request.get("case_id", "unknown"),
        "execution_status": status,
        "error_type": error_type[:120],
        "stdout_bytes": 0,
        "stderr_bytes": 0,
    }


def _validate_request(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise TypeError("request must be an object")
    required = {"case_id", "task_id", "task_revision", "entrypoint", "input"}
    if set(request) != required:
        raise ValueError("request fields are not the fixed runner contract")
    if (
        not isinstance(request["case_id"], str)
        or not 1 <= len(request["case_id"]) <= MAX_CASE_ID_LENGTH
        or not isinstance(request["task_id"], str)
    ):
        raise ValueError("invalid case identity")
    if not isinstance(request["task_revision"], int) or request["task_revision"] < 1:
        raise ValueError("invalid task revision")
    if not isinstance(request["entrypoint"], str) or not ENTRYPOINT_RE.fullmatch(
        request["entrypoint"]
    ):
        raise ValueError("invalid entrypoint")
    if not isinstance(request["input"], dict):
        raise TypeError("case input must be an object")
    return request


def _json_safe(value: Any) -> bool:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        return False
    return True


def execute(request: dict[str, Any], source: str) -> dict[str, Any]:
    stdout = LimitedTextIO(limit=16 * 1024)
    stderr = LimitedTextIO(limit=16 * 1024)
    try:
        compiled = compile(source, "/runner/student.py", "exec")
        namespace: dict[str, Any] = {
            "__name__": "__student__",
            "__file__": "/runner/student.py",
        }
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exec(compiled, namespace, namespace)  # noqa: S102
            function = namespace.get(request["entrypoint"])
            if not callable(function):
                raise TypeError("declared entrypoint is not callable")
            output = function(**request["input"])
        if not _json_safe(output):
            return {
                **_error_result(request, "INVALID_JSON", "NON_JSON_OUTPUT"),
                "stdout": stdout.getvalue(),
                "stderr": stderr.getvalue(),
                "stdout_bytes": stdout.size,
                "stderr_bytes": stderr.size,
            }
        return {
            "schema_version": "k12.runner.observation.v1",
            "case_id": request["case_id"],
            "execution_status": "COMPLETED",
            "actual_output": output,
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
            "stdout_bytes": stdout.size,
            "stderr_bytes": stderr.size,
        }
    except OutputLimitExceeded:
        return {
            **_error_result(request, "OUTPUT_LIMIT", "STUDENT_OUTPUT_LIMIT"),
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
            "stdout_bytes": stdout.size,
            "stderr_bytes": stderr.size,
        }
    except BaseException as exc:  # noqa: BLE001  (student code must not crash the protocol)
        return {
            **_error_result(request, "STUDENT_EXCEPTION", type(exc).__name__),
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
            "stdout_bytes": stdout.size,
            "stderr_bytes": stderr.size,
        }


def main() -> int:
    try:
        request = _validate_request(
            json.loads(REQUEST_PATH.read_text(encoding="utf-8"))
        )
        source = CODE_PATH.read_text(encoding="utf-8")
        result = execute(request, source)
    except BaseException as exc:  # noqa: BLE001  (malformed student input is a result)
        result = _error_result({}, "SYSTEM_ERROR", type(exc).__name__)
    sys.__stdout__.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n")
    sys.__stdout__.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
