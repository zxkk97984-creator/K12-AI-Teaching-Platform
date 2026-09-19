from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_id import REQUEST_ID_HEADER, request_id

ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "REVISION_CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    503: "SERVICE_UNAVAILABLE",
}


def envelope(code: str, message: str, request: Request, details: Any = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id(request),
            "details": details if details is not None else {},
        }
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = ERROR_CODES.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope(code, str(exc.detail), request),
            headers={REQUEST_ID_HEADER: request_id(request)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "location": list(item.get("loc", [])),
                "message": item.get("msg", "invalid value"),
                "type": item.get("type", "validation_error"),
            }
            for item in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=envelope("VALIDATION_ERROR", "请求参数无效", request, details),
            headers={REQUEST_ID_HEADER: request_id(request)},
        )

    @app.exception_handler(HTTPException)
    async def fastapi_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Do not leak exception strings, secrets, SQL or upstream payloads.
        return JSONResponse(
            status_code=500,
            content=envelope("INTERNAL_ERROR", "服务内部错误", request),
            headers={REQUEST_ID_HEADER: request_id(request)},
        )
