import uuid as _uuid

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.logging import get_logger
from app.middleware.request_id import REQUEST_ID_HEADER
from app.utils.sensitive_data import sanitize_error_message

logger = get_logger(__name__)


def _request_id_for(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    if rid:
        return rid
    return str(_uuid.uuid4())


class ExceptionMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)
        except StarletteHTTPException:
            raise
        except RequestValidationError:
            raise
        except Exception as exc:
            if exc.__class__.__name__ == "LLMDegradedError":
                raise
            return await unhandled_exception_handler(request, exc)


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    request_id = _request_id_for(request)
    logger.warning(
        "HTTP exception",
        status_code=exc.status_code,
        detail=str(exc.detail),
        path=request.url.path,
        request_id=request_id,
    )
    body: dict = {
        "detail": "REQUEST_ERROR",
        "message": str(exc.detail) if exc.status_code < 500 else "An error occurred",
        "request_id": request_id,
    }
    if exc.status_code >= 500:
        body["outcome"] = "terminal"
    return JSONResponse(
        status_code=exc.status_code,
        content=body,
        headers={REQUEST_ID_HEADER: request_id},
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    request_id = _request_id_for(request)
    logger.warning(
        "Validation error",
        errors=str(exc.errors()),
        path=request.url.path,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=422,
        content={
            "detail": "VALIDATION_ERROR",
            "message": "Invalid request data. Please check your input.",
            "request_id": request_id,
        },
        headers={REQUEST_ID_HEADER: request_id},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    try:
        request_id = _request_id_for(request)
    except Exception:
        request_id = str(_uuid.uuid4())
    try:
        logger.error(
            "unhandled_exception",
            error_type=type(exc).__name__,
            error=sanitize_error_message(str(exc)),
            path=str(request.url.path),
            method=request.method,
            request_id=request_id,
        )
    except Exception:
        pass
    return JSONResponse(
        status_code=500,
        content={
            "detail": "INTERNAL_SERVER_ERROR",
            "outcome": "terminal",
            "message": "An internal error occurred. Please try again later.",
            "request_id": request_id,
        },
        headers={REQUEST_ID_HEADER: request_id},
    )
