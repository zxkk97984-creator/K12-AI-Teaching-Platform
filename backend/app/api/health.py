from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.database import database_ready, engine_for
from app.core.errors import envelope
from app.core.request_id import request_id

router = APIRouter(tags=["health"])


def _runner_status(settings) -> str:
    if not settings.codelab_runner_url:
        return "disabled"
    try:
        with urllib.request.urlopen(
            f"{settings.codelab_runner_url.rstrip('/')}/health", timeout=1.5
        ) as response:
            body = json.loads(response.read(4096))
        return "ok" if body.get("status") == "ok" else "unavailable"
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        return "unavailable"


def _storage_status(settings) -> str:
    roots = (
        Path(settings.resource_storage_root),
        Path(settings.authoring_artifact_root),
        Path(settings.authoring_bundle_root),
    )
    return (
        "ok"
        if all(root.parent.exists() or root.parent.parent.exists() for root in roots)
        else "unavailable"
    )


@router.get("/health/live")
async def live(request: Request) -> dict[str, str]:
    return {"status": "ok", "service": "shuangling-k12", "request_id": request_id(request)}


@router.get("/health/ready")
async def ready(request: Request):
    try:
        engine = engine_for(request.app.state.settings)
        if not await database_ready(engine):
            raise RuntimeError("identity migration is not ready")
        runner = _runner_status(request.app.state.settings)
        storage = _storage_status(request.app.state.settings)
        if runner == "unavailable" or storage == "unavailable":
            raise RuntimeError("runner or storage is not ready")
    except Exception:
        return JSONResponse(
            status_code=503,
            content=envelope("SERVICE_UNAVAILABLE", "数据库尚未就绪", request),
        )
    return {
        "status": "ready",
        "database": "ok",
        "runner": _runner_status(request.app.state.settings),
        "storage": _storage_status(request.app.state.settings),
        "request_id": request_id(request),
    }
