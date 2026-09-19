from __future__ import annotations

import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

REQUEST_ID_HEADER = "X-Request-ID"
_VALID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def valid_request_id(value: str | None) -> str:
    if value and _VALID.fullmatch(value):
        return value
    return str(uuid.uuid4())


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = valid_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def request_id(request: Request) -> str:
    return getattr(
        request.state,
        "request_id",
        valid_request_id(request.headers.get(REQUEST_ID_HEADER)),
    )
