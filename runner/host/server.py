"""Small loopback control plane for the isolated runner.

This process, not FastAPI, owns the Docker launcher. It is intended for the
local T26 bridge and must remain loopback-bound with an explicit token.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from runner.host.runner import (
    DEFAULT_IMAGE,
    DockerRunner,
    InvalidRunRequest,
    RunnerUnavailable,
    RunRequest,
)


class RunnerHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class RunnerHandler(BaseHTTPRequestHandler):
    server_version = "K12Runner/0.1"

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            runner = self.server.runner  # type: ignore[attr-defined]
            try:
                runner.ensure_available()
            except RunnerUnavailable as exc:
                self._json(
                    503,
                    {
                        "status": "unavailable",
                        "ready": False,
                        "image": runner.image,
                        "error": str(exc),
                    },
                )
                return
            self._json(200, {"status": "ok", "ready": True, "image": runner.image})
            return
        self._json(404, {"error": "NOT_FOUND"})

    def do_POST(self) -> None:
        if self.path != "/v1/run":
            self._json(404, {"error": "NOT_FOUND"})
            return
        expected = self.server.control_token  # type: ignore[attr-defined]
        provided = self.headers.get("Authorization", "")
        if not expected or provided != f"Bearer {expected}":
            self._json(401, {"error": "UNAUTHORIZED"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 256 * 1024:
                raise ValueError("invalid request size")
            payload = json.loads(self.rfile.read(length))
            request = RunRequest.from_payload(payload)
            result = self.server.runner.run_case(request)  # type: ignore[attr-defined]
            self._json(200, result.as_observation() | {"code_hash": result.code_sha256})
        except InvalidRunRequest as exc:
            self._json(400, {"error": "INVALID_RUN_REQUEST", "message": str(exc)})
        except RunnerUnavailable as exc:
            self._json(503, {"error": "RUNNER_UNAVAILABLE", "message": str(exc)})
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "INVALID_JSON"})
        except Exception:  # noqa: BLE001  (control plane must return a safe error)
            self._json(500, {"error": "RUNNER_SYSTEM_ERROR"})

    def log_message(self, *_args: object) -> None:
        return None


def main() -> None:
    host = os.environ.get("RUNNER_HOST", "127.0.0.1")
    port = int(os.environ.get("RUNNER_PORT", "18090"))
    token = os.environ.get("RUNNER_CONTROL_TOKEN")
    if not token:
        raise SystemExit("RUNNER_CONTROL_TOKEN is required")
    server = RunnerHTTPServer((host, port), RunnerHandler)
    server.runner = DockerRunner(image=os.environ.get("RUNNER_IMAGE", DEFAULT_IMAGE))  # type: ignore[attr-defined]
    server.control_token = token  # type: ignore[attr-defined]
    server.serve_forever()


if __name__ == "__main__":
    main()
