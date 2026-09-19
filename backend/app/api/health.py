from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.database import database_ready, engine_for
from app.core.errors import envelope
from app.core.request_id import request_id

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live(request: Request) -> dict[str, str]:
    return {"status": "ok", "service": "shuangling-k12", "request_id": request_id(request)}


@router.get("/health/ready")
async def ready(request: Request):
    try:
        engine = engine_for(request.app.state.settings)
        if not await database_ready(engine):
            raise RuntimeError("identity migration is not ready")
    except Exception:
        return JSONResponse(
            status_code=503,
            content=envelope("SERVICE_UNAVAILABLE", "数据库尚未就绪", request),
        )
    return {"status": "ready", "database": "ok", "request_id": request_id(request)}
