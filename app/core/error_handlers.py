from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.logging import get_logger

logger = get_logger(__name__)


class ExceptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            return await unhandled_exception_handler(request, exc)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.warning(
        "http_exception",
        status_code=exc.status_code,
        detail=str(exc.detail),
        path=request.url.path,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "request_id": request_id},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    errors = []
    for error in exc.errors():
        loc = " -> ".join(str(l) for l in error["loc"])
        errors.append({"field": loc, "message": error["msg"]})
    logger.warning(
        "validation_error",
        errors=errors,
        path=request.url.path,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation error", "errors": errors, "request_id": request_id},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    try:
        request_id = getattr(request.state, "request_id", None)
    except Exception:
        request_id = None
    try:
        logger.exception(
            "unhandled_exception",
            error_type=type(exc).__name__,
            path=str(request.url.path),
            request_id=request_id,
        )
    except Exception:
        pass
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )
