"""HTTP transport half of the Knodo adapter (no wire mapper in T10).

The transport normalises status codes, timeouts, cancellation, malformed JSON
and output-size overflow into :class:`BackendOutcome`. It performs exactly one
POST per call: there is no retry path, so a cancelled or timed-out call can
never turn into a billable retry or a ghost success.

Exception text and upstream bodies are never copied into errors or logs; only
the HTTP status code travels. ``WireMapper`` is intentionally absent until T11
produces evidence-backed field mappings, so the gateway refuses to call this
transport today.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.integrations.knodo.errors import (
    GatewayError,
    GatewayErrorCategory,
    classify_upstream_status,
    error_from_status,
)
from app.integrations.knodo.types import BackendOutcome


@dataclass(frozen=True)
class UpstreamRequest:
    """A mapped upstream call. ``headers`` may carry credentials: never log it."""

    url: str
    payload: dict[str, Any]
    headers: dict[str, str]
    request_id: str


class Transport(Protocol):
    async def send(
        self,
        request: UpstreamRequest,
        *,
        timeout_seconds: float,
        cancel: asyncio.Event | None = None,
    ) -> BackendOutcome: ...


class HttpTransport:
    def __init__(self, client: httpx.AsyncClient, *, max_output_bytes: int):
        self._client = client
        self.max_output_bytes = max_output_bytes

    async def aclose(self) -> None:
        await self._client.aclose()

    async def send(
        self,
        request: UpstreamRequest,
        *,
        timeout_seconds: float,
        cancel: asyncio.Event | None = None,
    ) -> BackendOutcome:
        return await self._send_guarded(request, timeout_seconds=timeout_seconds, cancel=cancel)

    async def send_stream(
        self,
        request: UpstreamRequest,
        *,
        timeout_seconds: float,
        cancel: asyncio.Event | None = None,
        on_content: Callable[[str], Awaitable[None]],
    ) -> BackendOutcome:
        """Consume one OpenAI-compatible SSE POST; never retry an uncertain call."""

        return await self._send_guarded(
            request, timeout_seconds=timeout_seconds, cancel=cancel, on_content=on_content
        )

    async def _send_guarded(
        self,
        request: UpstreamRequest,
        *,
        timeout_seconds: float,
        cancel: asyncio.Event | None,
        on_content: Callable[[str], Awaitable[None]] | None = None,
    ) -> BackendOutcome:
        if cancel is not None and cancel.is_set():
            return BackendOutcome(cancelled=True)

        post_task = asyncio.create_task(
            self._send_once(request, timeout_seconds=timeout_seconds, on_content=on_content)
        )
        cancel_task = asyncio.create_task(cancel.wait()) if cancel is not None else None
        try:
            waiters: set[asyncio.Task[Any]] = {post_task}
            if cancel_task is not None:
                waiters.add(cancel_task)
            done, _ = await asyncio.wait(
                waiters, timeout=timeout_seconds, return_when=asyncio.FIRST_COMPLETED
            )
            if not done:
                post_task.cancel()
                return BackendOutcome(
                    error=GatewayError(
                        GatewayErrorCategory.TIMEOUT,
                        "UPSTREAM_TIMEOUT_ACCEPTANCE_UNKNOWN",
                    ),
                    upstream_calls=1,
                )
            if cancel_task is not None and cancel_task in done and cancel_task.result():
                # Cancel wins over a racing success: no ghost success, no retry.
                post_task.cancel()
                return BackendOutcome(cancelled=True, upstream_calls=1)
            return await post_task
        except httpx.TimeoutException:
            return BackendOutcome(
                error=GatewayError(
                    GatewayErrorCategory.TIMEOUT,
                    "UPSTREAM_TIMEOUT_ACCEPTANCE_UNKNOWN",
                ),
                upstream_calls=1,
            )
        except TimeoutError:
            return BackendOutcome(
                error=GatewayError(
                    GatewayErrorCategory.TIMEOUT,
                    "UPSTREAM_TIMEOUT_ACCEPTANCE_UNKNOWN",
                ),
                upstream_calls=1,
            )
        except httpx.ConnectError:
            return BackendOutcome(
                error=GatewayError(GatewayErrorCategory.UNKNOWN, "UPSTREAM_CONNECTION_ERROR"),
                upstream_calls=1,
            )
        except httpx.HTTPError:
            # A read/protocol failure may happen after the server accepted the
            # POST. Never retry it automatically or surface exception details.
            return BackendOutcome(
                error=GatewayError(GatewayErrorCategory.UNKNOWN, "UPSTREAM_ACCEPTANCE_UNKNOWN"),
                upstream_calls=1,
            )
        finally:
            if cancel_task is not None:
                cancel_task.cancel()
            if not post_task.done():
                post_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await post_task

    async def _send_once(
        self,
        request: UpstreamRequest,
        *,
        timeout_seconds: float,
        on_content: Callable[[str], Awaitable[None]] | None = None,
    ) -> BackendOutcome:
        async with self._client.stream(
            "POST",
            request.url,
            json=request.payload,
            headers=request.headers,
            timeout=timeout_seconds,
        ) as response:
            category = classify_upstream_status(response.status_code)
            if category is not None:
                return BackendOutcome(
                    error=error_from_status(response.status_code),
                    upstream_calls=1,
                )

            content_type = response.headers.get("content-type", "").lower()
            if on_content is not None and "text/event-stream" in content_type:
                return await self._consume_sse(response, on_content=on_content)
            if on_content is not None and "json" not in content_type:
                return self._stream_invalid("UPSTREAM_STREAM_CONTENT_TYPE_INVALID")

            # A provider that ignores stream=true may return the ordinary
            # completion. Consume that same one response without re-sending.

            content = bytearray()
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > self.max_output_bytes:
                    return BackendOutcome(
                        error=GatewayError(
                            GatewayErrorCategory.OUTPUT_LIMIT,
                            "UPSTREAM_OUTPUT_TOO_LARGE",
                            upstream_status=response.status_code,
                        ),
                        upstream_calls=1,
                    )
            try:
                payload = json.loads(bytes(content) or b"{}")
            except (json.JSONDecodeError, UnicodeDecodeError):
                return BackendOutcome(
                    error=GatewayError(
                        GatewayErrorCategory.VALIDATION,
                        "UPSTREAM_MALFORMED_JSON",
                    ),
                    upstream_calls=1,
                )
            if not isinstance(payload, dict):
                return BackendOutcome(
                    error=GatewayError(
                        GatewayErrorCategory.VALIDATION,
                        "UPSTREAM_NOT_AN_OBJECT",
                    ),
                    upstream_calls=1,
                )
            return BackendOutcome(payload=payload, upstream_calls=1)

    async def _consume_sse(
        self,
        response: httpx.Response,
        *,
        on_content: Callable[[str], Awaitable[None]],
    ) -> BackendOutcome:
        content = ""
        completion_id: str | None = None
        model: str | None = None
        conversation_id: str | None = None
        finish_reason: str | None = None
        saw_done = False
        size = 0
        # SSE repeats a JSON envelope for each tiny delta. Bound those wire
        # bytes separately from the decoded assistant content budget.
        max_wire_bytes = min(8 * 1024 * 1024, max(2 * 1024 * 1024, self.max_output_bytes * 4))
        data_lines: list[str] = []

        async def consume_event() -> BackendOutcome | None:
            nonlocal content, completion_id, model, conversation_id, finish_reason, saw_done
            if not data_lines:
                return None
            data = "\n".join(data_lines)
            data_lines.clear()
            if data == "[DONE]":
                saw_done = True
                return None
            try:
                event = json.loads(data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return self._stream_invalid("UPSTREAM_STREAM_MALFORMED_JSON")
            if not isinstance(event, dict) or event.get("error") is not None:
                return self._stream_invalid("UPSTREAM_STREAM_REPORTED_ERROR")
            if event.get("object") != "chat.completion.chunk":
                return self._stream_invalid("UPSTREAM_STREAM_SHAPE_INVALID")
            for key, previous in (
                ("id", completion_id),
                ("model", model),
                ("conversationId", conversation_id),
            ):
                value = event.get(key)
                if value is not None and (
                    not isinstance(value, str) or not value or (previous and value != previous)
                ):
                    return self._stream_invalid("UPSTREAM_STREAM_SHAPE_INVALID")
            completion_id = event.get("id") or completion_id
            model = event.get("model") or model
            conversation_id = event.get("conversationId") or conversation_id
            choices = event.get("choices")
            if not isinstance(choices, list):
                return self._stream_invalid("UPSTREAM_STREAM_SHAPE_INVALID")
            if not choices:
                return None  # optional final usage frame
            if len(choices) != 1 or not isinstance(choices[0], dict):
                return self._stream_invalid("UPSTREAM_STREAM_SHAPE_INVALID")
            choice = choices[0]
            if choice.get("index") != 0:
                return self._stream_invalid("UPSTREAM_STREAM_SHAPE_INVALID")
            delta = choice.get("delta")
            if not isinstance(delta, dict) or delta.get("role", "assistant") != "assistant":
                return self._stream_invalid("UPSTREAM_STREAM_SHAPE_INVALID")
            if any(key in delta for key in ("tool_calls", "function_call")):
                return self._stream_invalid("UPSTREAM_STREAM_SHAPE_INVALID")
            piece = delta.get("content")
            if piece is not None:
                if not isinstance(piece, str) or finish_reason is not None:
                    return self._stream_invalid("UPSTREAM_STREAM_SHAPE_INVALID")
                content += piece
                try:
                    content_bytes = len(content.encode("utf-8"))
                except UnicodeEncodeError:
                    return self._stream_invalid("UPSTREAM_STREAM_SHAPE_INVALID")
                if content_bytes > self.max_output_bytes:
                    return BackendOutcome(
                        error=GatewayError(
                            GatewayErrorCategory.OUTPUT_LIMIT, "UPSTREAM_OUTPUT_TOO_LARGE"
                        ),
                        upstream_calls=1,
                    )
                await on_content(content)
            reason = choice.get("finish_reason")
            if reason is not None:
                if not isinstance(reason, str) or finish_reason is not None:
                    return self._stream_invalid("UPSTREAM_STREAM_SHAPE_INVALID")
                finish_reason = reason
            return None

        async for line in response.aiter_lines():
            try:
                line_bytes = len(line.encode("utf-8"))
            except UnicodeEncodeError:
                return self._stream_invalid("UPSTREAM_STREAM_SHAPE_INVALID")
            if line_bytes > 64 * 1024:
                return BackendOutcome(
                    error=GatewayError(
                        GatewayErrorCategory.OUTPUT_LIMIT, "UPSTREAM_OUTPUT_TOO_LARGE"
                    ),
                    upstream_calls=1,
                )
            size += line_bytes + 1
            if size > max_wire_bytes:
                return BackendOutcome(
                    error=GatewayError(
                        GatewayErrorCategory.OUTPUT_LIMIT, "UPSTREAM_OUTPUT_TOO_LARGE"
                    ),
                    upstream_calls=1,
                )
            if not line:
                error = await consume_event()
                if error is not None:
                    return error
                if saw_done:
                    break
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip(" "))
        if data_lines and not saw_done:
            error = await consume_event()
            if error is not None:
                return error
        # Knodo's Bot Chat stream can end cleanly after its terminal chunk
        # (finish_reason=stop, conversationId) without an OpenAI [DONE] line.
        # An abrupt transport failure raises before this point; a stream with
        # no terminal finish_reason remains incomplete.
        if finish_reason is None:
            return self._stream_invalid("UPSTREAM_STREAM_INCOMPLETE")
        payload = {
            "id": completion_id,
            "object": "chat.completion",
            "model": model,
            "conversationId": conversation_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": finish_reason,
                }
            ],
        }
        return BackendOutcome(payload=payload, upstream_calls=1)

    @staticmethod
    def _stream_invalid(code: str) -> BackendOutcome:
        return BackendOutcome(
            error=GatewayError(GatewayErrorCategory.VALIDATION, code),
            upstream_calls=1,
        )
