"""T10/QA11: transport normalisation, cancellation and leak-free failures.

These tests inject ``httpx.MockTransport``: they prove *our* adapter behaviour,
not Knodo compatibility. The official wire mapper is T11 work.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.integrations.knodo.transport import HttpTransport, UpstreamRequest

PAT = "pat-synthetic-3a5f9c2b7d1e4f60"


def make_request() -> UpstreamRequest:
    return UpstreamRequest(
        url="https://knodo.invalid/api/simple",
        payload={"synthetic": True},
        headers={"Authorization": f"Bearer {PAT}"},
        request_id="synthetic-request-1",
    )


class Handler:
    def __init__(
        self,
        *,
        status: int = 200,
        body: bytes | None = None,
        exc: Exception | None = None,
        delay: float = 0.0,
    ):
        self.status = status
        self.body = body if body is not None else json.dumps({"ok": True}).encode()
        self.exc = exc
        self.delay = delay
        self.calls = 0

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc is not None:
            raise self.exc
        return httpx.Response(self.status, content=self.body, request=request)


class CountingStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]):
        self.chunks = chunks
        self.yielded = 0

    async def __aiter__(self):
        for chunk in self.chunks:
            self.yielded += 1
            yield chunk


def build_transport(handler: Handler, *, max_output_bytes: int = 4096) -> HttpTransport:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HttpTransport(client, max_output_bytes=max_output_bytes)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "category"),
    [
        (401, "AUTH"),
        (403, "AUTH"),
        (429, "RATE"),
        (500, "SERVER"),
        (503, "SERVER"),
        (302, "UNKNOWN"),
        (418, "UNKNOWN"),
    ],
)
async def test_status_codes_map_to_the_taxonomy(status: int, category: str) -> None:
    handler = Handler(status=status)
    outcome = await build_transport(handler).send(make_request(), timeout_seconds=2)
    assert outcome.error is not None
    assert outcome.error.category.value == category
    assert outcome.error.upstream_status == status
    assert outcome.payload is None
    assert handler.calls == 1  # single POST: no retry semantics


@pytest.mark.asyncio
async def test_success_returns_the_parsed_object() -> None:
    handler = Handler(body=json.dumps({"result": "synthetic"}).encode())
    outcome = await build_transport(handler).send(make_request(), timeout_seconds=2)
    assert outcome.error is None
    assert outcome.payload == {"result": "synthetic"}
    assert outcome.upstream_calls == 1


@pytest.mark.asyncio
async def test_malformed_or_non_object_body_is_rejected_without_leaking_it() -> None:
    leak = f"broken json containing {PAT}"
    truncated = Handler(body=leak.encode())
    outcome = await build_transport(truncated).send(make_request(), timeout_seconds=2)
    assert outcome.error is not None
    assert outcome.error.category.value == "VALIDATION"
    assert outcome.error.reason_code == "UPSTREAM_MALFORMED_JSON"
    assert PAT not in json.dumps(outcome.error.to_public())

    array_body = Handler(body=json.dumps([1, 2, 3]).encode())
    outcome = await build_transport(array_body).send(make_request(), timeout_seconds=2)
    assert outcome.error is not None
    assert outcome.error.reason_code == "UPSTREAM_NOT_AN_OBJECT"


@pytest.mark.asyncio
async def test_output_size_limit_is_enforced_before_parsing() -> None:
    handler = Handler(body=b'{"blob": "' + b"x" * 5000 + b'"}')
    outcome = await build_transport(handler, max_output_bytes=1024).send(
        make_request(), timeout_seconds=2
    )
    assert outcome.error is not None
    assert outcome.error.category.value == "OUTPUT_LIMIT"
    assert outcome.error.reason_code == "UPSTREAM_OUTPUT_TOO_LARGE"


@pytest.mark.asyncio
async def test_output_limit_stops_reading_the_stream() -> None:
    stream = CountingStream([b"x" * 600, b"y" * 600, b"z" * 600])

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = HttpTransport(client, max_output_bytes=1024)
    outcome = await transport.send(make_request(), timeout_seconds=2)
    await transport.aclose()

    assert outcome.error is not None
    assert outcome.error.reason_code == "UPSTREAM_OUTPUT_TOO_LARGE"
    assert stream.yielded == 2


@pytest.mark.asyncio
async def test_timeout_becomes_a_predictable_error() -> None:
    handler = Handler(exc=httpx.ReadTimeout("synthetic timeout"))
    outcome = await build_transport(handler).send(make_request(), timeout_seconds=2)
    assert outcome.error is not None
    assert outcome.error.category.value == "TIMEOUT"
    assert outcome.error.reason_code == "UPSTREAM_TIMEOUT_ACCEPTANCE_UNKNOWN"
    assert handler.calls == 1

    slow = Handler(delay=0.5)
    outcome = await build_transport(slow).send(make_request(), timeout_seconds=0.05)
    assert outcome.error is not None
    assert outcome.error.category.value == "TIMEOUT"
    assert outcome.error.reason_code == "UPSTREAM_TIMEOUT_ACCEPTANCE_UNKNOWN"
    assert slow.calls == 1


@pytest.mark.asyncio
async def test_read_failure_is_accepted_unknown_and_never_retried() -> None:
    handler = Handler(exc=httpx.ReadError("synthetic read failure after send"))
    outcome = await build_transport(handler).send(make_request(), timeout_seconds=2)
    assert outcome.error is not None
    assert outcome.error.category.value == "UNKNOWN"
    assert outcome.error.reason_code == "UPSTREAM_ACCEPTANCE_UNKNOWN"
    assert handler.calls == 1


@pytest.mark.asyncio
async def test_connection_errors_never_carry_exception_text() -> None:
    handler = Handler(exc=httpx.ConnectError(f"failed with {PAT} and cookie sl_session=abc123"))
    outcome = await build_transport(handler).send(make_request(), timeout_seconds=2)
    assert outcome.error is not None
    assert outcome.error.category.value == "UNKNOWN"
    public = json.dumps(outcome.error.to_public())
    assert PAT not in public
    assert "sl_session" not in public
    assert "abc123" not in public


@pytest.mark.asyncio
async def test_pre_set_cancel_short_circuits_without_an_upstream_call() -> None:
    handler = Handler()
    cancel = asyncio.Event()
    cancel.set()
    outcome = await build_transport(handler).send(make_request(), timeout_seconds=2, cancel=cancel)
    assert outcome.cancelled is True
    assert outcome.payload is None
    assert handler.calls == 0


@pytest.mark.asyncio
async def test_midflight_cancel_wins_over_a_racing_success() -> None:
    handler = Handler(delay=0.3)
    cancel = asyncio.Event()

    async def signal() -> None:
        await asyncio.sleep(0.05)
        cancel.set()

    signaller = asyncio.create_task(signal())
    outcome = await build_transport(handler).send(make_request(), timeout_seconds=2, cancel=cancel)
    await signaller
    assert outcome.cancelled is True
    assert outcome.payload is None
    assert handler.calls == 1  # cancelled call is never retried
