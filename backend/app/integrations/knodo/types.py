"""Result types for the gateway: predictable outcomes, no bare exceptions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.integrations.knodo.errors import GatewayError, GatewayErrorCategory
from app.integrations.knodo.operations import Operation

GatewayMode = Literal["disabled", "fixture", "knodo"]


class GatewayStatus(StrEnum):
    OK = "OK"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class GatewayErrorInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: GatewayErrorCategory
    reason_code: str
    message: str
    upstream_status: int | None = None

    @classmethod
    def from_error(cls, error: GatewayError) -> GatewayErrorInfo:
        public = error.to_public()
        return cls(
            category=error.category,
            reason_code=error.reason_code,
            message=error.public_message,
            upstream_status=public.get("upstream_status"),  # type: ignore[arg-type]
        )


class GatewayUsage(BaseModel):
    """Per-invocation accounting. Never shared between concurrent requests."""

    model_config = ConfigDict(frozen=True)

    input_bytes: int
    output_bytes: int
    duration_ms: int
    upstream_calls: int


class GatewayResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    invocation_id: str
    operation: Operation
    mode: GatewayMode
    status: GatewayStatus
    output: dict[str, Any] | None
    error: GatewayErrorInfo | None
    usage: GatewayUsage
    remote_metadata: dict[str, Any] | None = None
    fixture: bool
    fixture_notice: str | None = None


@dataclass(frozen=True)
class BackendOutcome:
    """What a backend (fixture / knodo) hands back before the gateway judges it."""

    payload: dict[str, Any] | None = None
    error: GatewayError | None = None
    cancelled: bool = False
    insufficient_evidence: bool = False
    upstream_calls: int = 0
    remote_metadata: dict[str, Any] | None = None
