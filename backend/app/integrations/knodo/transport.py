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
        if cancel is not None and cancel.is_set():
            return BackendOutcome(cancelled=True)

        post_task = asyncio.create_task(self._send_once(request, timeout_seconds=timeout_seconds))
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
