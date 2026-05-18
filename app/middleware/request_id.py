from __future__ import annotations

import uuid
from typing import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_CONTEXT_KEY = "request_id"


def _coerce_request_id(value: str | None) -> str:
    if value is None:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        return str(uuid.uuid4())


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = _coerce_request_id(incoming)

        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(**{REQUEST_ID_CONTEXT_KEY: request_id})

        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars(REQUEST_ID_CONTEXT_KEY)

        response.headers[REQUEST_ID_HEADER] = request_id
        return response
