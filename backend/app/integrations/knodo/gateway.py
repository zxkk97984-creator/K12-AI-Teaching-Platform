"""Single entry point for the four fixed agent operations.

``AgentGateway.invoke`` is the only business-facing call. It parses the
operation (fail-closed on anything outside the fixed four), validates the
request against the frozen T03 schema, dispatches to the configured backend,
enforces the output byte budget, validates the response against the frozen
schema and returns a :class:`GatewayResult`.

Fail-closed rules (QA38):

* ``disabled`` never falls back to fixture or a direct LLM call;
* ``fixture`` is rejected in production (settings + defence in depth here);
* ``knodo`` requires a bare HTTPS origin, token, fixed Tutor/Designer targets,
  an explicit unlimited or finite request policy and the frozen contract files; it never silently
  degrades to the fixture.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.integrations.knodo.budget import FileRequestBudget, UnlimitedRequestBudget
from app.integrations.knodo.errors import (
    GatewayError,
    GatewayErrorCategory,
)
from app.integrations.knodo.fixture import FIXTURE_NOTICE, FixtureGateway, FixtureScenario
from app.integrations.knodo.operations import (
    OPERATION_SPECS,
    Operation,
    UnknownOperation,
    parse_operation,
)
from app.integrations.knodo.schema_models import (
    MissingContractSchema,
    SchemaRegistry,
    default_registry,
)
from app.integrations.knodo.transport import HttpTransport
from app.integrations.knodo.types import (
    GatewayErrorInfo,
    GatewayMode,
    GatewayResult,
    GatewayStatus,
    GatewayUsage,
)
from app.integrations.knodo.wire import KnodoTarget, KnodoWireMapper

WIRE_MAPPER_STATUS = "KNODO_BOT_CHAT_V1"


class GatewayConfigurationError(RuntimeError):
    """Raised when the requested gateway mode cannot be served safely."""


@dataclass(frozen=True)
class GatewayRuntimeStatus:
    mode: GatewayMode
    available: bool
    reason_code: str
    wire_mapper: str
    fixture: bool
    contract_version: str | None

    def to_public(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "available": self.available,
            "reason_code": self.reason_code,
            "wire_mapper": self.wire_mapper,
            "fixture": self.fixture,
            "contract_version": self.contract_version,
            "operations": [
                {"id": spec.operation.value, "role": spec.role} for spec in OPERATION_SPECS.values()
            ],
        }


class AgentGateway:
    def __init__(
        self,
        *,
        mode: GatewayMode,
        registry: SchemaRegistry,
        backend: FixtureGateway | KnodoWireMapper | None = None,
        timeout_seconds: float,
        max_output_bytes: int,
        unavailable_reason: str | None = None,
    ):
        self.mode = mode
        self.registry = registry
        self._backend = backend
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self._unavailable_reason = unavailable_reason

    async def aclose(self) -> None:
        closer = getattr(self._backend, "aclose", None)
        if closer is not None:
            await closer()

    def continuation_scope(
        self, operation: str | Operation, *, target: KnodoTarget | None = None
    ) -> str | None:
        builder = getattr(self._backend, "continuation_scope", None)
        if builder is None:
            return None
        try:
            parsed = parse_operation(operation)
        except UnknownOperation:
            return None
        contract_version = self.registry.contract_version
        if not contract_version:
            return None
        return builder(
            parsed, contract_version=contract_version, **({"target": target} if target else {})
        )

    # -- status ---------------------------------------------------------- #
    @property
    def status(self) -> GatewayRuntimeStatus:
        available = self._backend is not None and self._unavailable_reason is None
        reason = self._unavailable_reason or ("AVAILABLE" if available else "GATEWAY_DISABLED")
        return GatewayRuntimeStatus(
            mode=self.mode,
            available=available,
            reason_code=reason,
            wire_mapper=WIRE_MAPPER_STATUS if self.mode == "knodo" else "NOT_APPLICABLE",
            fixture=self.mode == "fixture",
            contract_version=self.registry.contract_version,
        )

    # -- the single business entry point --------------------------------- #
    async def invoke(
        self,
        operation: str | Operation,
        payload: Any,
        *,
        target: KnodoTarget | None = None,
        scenario: FixtureScenario = FixtureScenario.SUCCESS,
        timeout_seconds: float | None = None,
        cancel: Any = None,
        delay_seconds: float | None = None,
        remote_conversation_id: str | None = None,
        on_content: Callable[[str], Awaitable[None]] | None = None,
    ) -> GatewayResult:
        invocation_id = str(uuid.uuid4())
        started = time.perf_counter()
        input_bytes = self._byte_length(payload)

        def fail(
            error: GatewayError,
            *,
            upstream_calls: int = 0,
            remote_metadata: dict[str, Any] | None = None,
        ) -> GatewayResult:
            return self._result(
                invocation_id=invocation_id,
                operation=self._safe_operation(operation),
                status=GatewayStatus.FAILED,
                output=None,
                error=GatewayErrorInfo.from_error(error),
                started=started,
                input_bytes=input_bytes or 0,
                output_bytes=0,
                upstream_calls=upstream_calls,
                remote_metadata=remote_metadata,
            )

        if self._backend is None:
            return fail(
                GatewayError(
                    GatewayErrorCategory.CONFIG,
                    self._unavailable_reason or "GATEWAY_DISABLED",
                )
            )

        try:
            parsed = parse_operation(operation)
        except UnknownOperation:
            return fail(
                GatewayError(GatewayErrorCategory.UNSUPPORTED_OPERATION, "UNKNOWN_OPERATION")
            )

        if input_bytes is None:
            return fail(GatewayError(GatewayErrorCategory.VALIDATION, "REQUEST_NOT_SERIALIZABLE"))
        request_problems = self.registry.validate_request(parsed, payload)
        if request_problems:
            return fail(GatewayError(GatewayErrorCategory.VALIDATION, "REQUEST_SCHEMA_MISMATCH"))

        outcome = await self._backend.invoke(
            parsed,
            payload,
            **({"target": target} if target and self.mode == "knodo" else {}),
            scenario=scenario,
            timeout_seconds=timeout_seconds or self.timeout_seconds,
            cancel=cancel,
            delay_seconds=delay_seconds,
            remote_conversation_id=remote_conversation_id,
            on_content=on_content,
        )
        if outcome.cancelled:
            return self._result(
                invocation_id=invocation_id,
                operation=parsed,
                status=GatewayStatus.CANCELLED,
                output=None,
                error=GatewayErrorInfo.from_error(
                    GatewayError(GatewayErrorCategory.CANCEL, "CALL_CANCELLED")
                ),
                started=started,
                input_bytes=input_bytes,
                output_bytes=0,
                upstream_calls=outcome.upstream_calls,
            )
        if outcome.error is not None:
            return fail(
                outcome.error,
                upstream_calls=outcome.upstream_calls,
                remote_metadata=outcome.remote_metadata,
            )

        payload_out = outcome.payload or {}
        output_bytes = self._byte_length(payload_out)
        if output_bytes is None:
            return fail(
                GatewayError(GatewayErrorCategory.VALIDATION, "OUTPUT_NOT_SERIALIZABLE"),
                remote_metadata=outcome.remote_metadata,
            )
        if output_bytes > self.max_output_bytes:
            return fail(
                GatewayError(GatewayErrorCategory.OUTPUT_LIMIT, "OUTPUT_LIMIT_EXCEEDED"),
                upstream_calls=outcome.upstream_calls,
                remote_metadata=outcome.remote_metadata,
            )
        response_problems = self.registry.validate_response(parsed, payload_out)
        if response_problems:
            return fail(
                GatewayError(GatewayErrorCategory.VALIDATION, "RESPONSE_SCHEMA_MISMATCH"),
                upstream_calls=outcome.upstream_calls,
                remote_metadata=outcome.remote_metadata,
            )

        return self._result(
            invocation_id=invocation_id,
            operation=parsed,
            status=(
                GatewayStatus.INSUFFICIENT_EVIDENCE
                if outcome.insufficient_evidence
                else GatewayStatus.OK
            ),
            output=payload_out,
            error=None,
            started=started,
            input_bytes=input_bytes,
            output_bytes=output_bytes,
            upstream_calls=outcome.upstream_calls,
            remote_metadata=outcome.remote_metadata,
        )

    # -- helpers --------------------------------------------------------- #
    def _safe_operation(self, operation: Any) -> Operation:
        try:
            return parse_operation(operation)
        except UnknownOperation:
            return Operation.TEACH_TURN  # placeholder only; status is FAILED

    @staticmethod
    def _byte_length(value: Any) -> int | None:
        try:
            return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
        except (TypeError, ValueError):
            return None

    def _result(
        self,
        *,
        invocation_id: str,
        operation: Operation,
        status: GatewayStatus,
        output: dict[str, Any] | None,
        error: GatewayErrorInfo | None,
        started: float,
        input_bytes: int,
        output_bytes: int,
        upstream_calls: int,
        remote_metadata: dict[str, Any] | None = None,
    ) -> GatewayResult:
        fixture = self.mode == "fixture"
        return GatewayResult(
            invocation_id=invocation_id,
            operation=operation,
            mode=self.mode,
            status=status,
            output=output,
            error=error,
            usage=GatewayUsage(
                input_bytes=input_bytes,
                output_bytes=output_bytes,
                duration_ms=int((time.perf_counter() - started) * 1000),
                upstream_calls=upstream_calls,
            ),
            remote_metadata=remote_metadata,
            fixture=fixture,
            fixture_notice=FIXTURE_NOTICE if fixture else None,
        )


def build_gateway(settings: Any) -> AgentGateway:
    """Build the gateway for the configured mode, or fail closed."""

    try:
        registry = default_registry()
    except MissingContractSchema as exc:
        raise GatewayConfigurationError(f"frozen contract files unavailable: {exc}") from exc

    mode: Literal["disabled", "fixture", "knodo"] = settings.gateway_mode
    timeout_seconds = float(settings.gateway_timeout_seconds)
    max_output_bytes = int(settings.gateway_max_output_bytes)

    if mode == "disabled":
        return AgentGateway(
            mode="disabled",
            registry=registry,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
            unavailable_reason="GATEWAY_DISABLED",
        )

    if mode == "fixture":
        if settings.app_env == "production":
            raise GatewayConfigurationError("fixture gateway mode is forbidden in production")
        return AgentGateway(
            mode="fixture",
            registry=registry,
            backend=FixtureGateway(
                max_output_bytes=max_output_bytes, default_timeout_seconds=timeout_seconds
            ),
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        )

    if mode == "knodo":
        if not settings.knodo_base_url:
            raise GatewayConfigurationError("KNODO_BASE_URL is required when GATEWAY_MODE=knodo")
        token = os.environ.get(settings.knodo_token_env_var, "")
        if not token:
            raise GatewayConfigurationError(
                f"environment variable {settings.knodo_token_env_var} is not set"
            )
        try:
            targets = {
                role: KnodoTarget(
                    bot_id=getattr(settings, f"knodo_{role}_bot_id"),
                    workspace_id=getattr(settings, f"knodo_{role}_workspace_id"),
                )
                for role in ("tutor", "designer")
                if getattr(settings, f"knodo_{role}_bot_id", None)
                and getattr(settings, f"knodo_{role}_workspace_id", None)
            }
            max_requests = int(settings.knodo_max_requests)
            budget = (
                UnlimitedRequestBudget()
                if max_requests == 0
                else FileRequestBudget(
                    settings.knodo_budget_ledger_path,
                    max_requests=max_requests,
                )
            )
            # Redirects are intentionally disabled so credentials never follow
            # an upstream Location header to a different origin. Environment
            # proxy variables are ignored for the same credential boundary.
            client = httpx.AsyncClient(follow_redirects=False, trust_env=False)
            backend = KnodoWireMapper(
                base_url=settings.knodo_base_url,
                token=token,
                targets=targets,
                transport=HttpTransport(client, max_output_bytes=max_output_bytes),
                budget=budget,
                stream_timeout_seconds=settings.knodo_stream_timeout_seconds,
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise GatewayConfigurationError("invalid Knodo target or budget configuration") from exc
        return AgentGateway(
            mode="knodo",
            registry=registry,
            backend=backend,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        )

    raise GatewayConfigurationError(f"unsupported gateway mode: {mode!r}")
