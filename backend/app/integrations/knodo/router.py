"""Read-only capability status for the AI gateway.

Deliberately free of secrets: no base URL, no token state, no environment
variable names. The endpoint exists so a UI or an operator can tell whether the
AI path is actually available instead of assuming the fixture is real.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(prefix="/ai/gateway", tags=["ai-gateway"])


@router.get("/status")
def gateway_status(request: Request) -> dict[str, Any]:
    gateway = request.app.state.gateway
    return gateway.status.to_public()
