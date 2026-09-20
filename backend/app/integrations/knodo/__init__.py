"""Knodo agent gateway: four fixed operations, honest fixture, fail-closed modes."""

from app.integrations.knodo.errors import GatewayError, GatewayErrorCategory
from app.integrations.knodo.gateway import (
    AgentGateway,
    GatewayConfigurationError,
    GatewayRuntimeStatus,
    build_gateway,
)
from app.integrations.knodo.operations import (
    DESIGNER_OPERATIONS,
    OPERATION_SPECS,
    TUTOR_OPERATIONS,
    Operation,
    UnknownOperation,
    parse_operation,
)
from app.integrations.knodo.types import GatewayResult, GatewayStatus, GatewayUsage
from app.integrations.knodo.wire import KnodoTarget, KnodoWireMapper

__all__ = [
    "AgentGateway",
    "DESIGNER_OPERATIONS",
    "GatewayConfigurationError",
    "GatewayError",
    "GatewayErrorCategory",
    "GatewayResult",
    "GatewayRuntimeStatus",
    "GatewayStatus",
    "GatewayUsage",
    "KnodoTarget",
    "KnodoWireMapper",
    "OPERATION_SPECS",
    "Operation",
    "TUTOR_OPERATIONS",
    "UnknownOperation",
    "build_gateway",
    "parse_operation",
]
