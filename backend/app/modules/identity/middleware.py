from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.errors import envelope
from app.modules.identity.dependencies import assert_csrf

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class SameOriginCsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/v1/") and request.method in UNSAFE_METHODS:
            settings = request.app.state.settings
            try:
                assert_csrf(
                    request,
                    settings,
                    request.headers.get("Origin"),
                    request.headers.get("X-CSRF-Token"),
                    request.cookies.get("sl_csrf"),
                )
            except HTTPException as exc:
                allowed = {"CSRF_ORIGIN_FAILED", "CSRF_TOKEN_INVALID"}
                code = str(exc.detail) if exc.detail in allowed else "CSRF_CHECK_FAILED"
                return JSONResponse(
                    status_code=403,
                    content=envelope(code, "同源校验失败", request),
                )
        response = await call_next(request)
        if request.url.path.startswith("/api/v1/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response
