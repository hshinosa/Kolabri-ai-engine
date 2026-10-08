"""
Kolabri AI-Engine
=================
FastAPI backend for AI computation, RAG pipeline, and LLM integration.
Uses GLM-4.7 (OpenAI Compatible) as the primary LLM provider.
"""

import os

# Wajib sebelum import modul app: flags PaddleX dibaca sekali saat
# `import paddleocr` pertama (default OneDNN menyebabkan bug PIR pada CPU ini).
os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "true")

import uvicorn
import asyncio
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager
from typing import Optional

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.api.routes import router as api_router
from app.services.vector_store import get_vector_store
from app.services.mongodb_logger import get_mongo_logger
from app.services.logic_listener import get_logic_listener
from app.services.notification_service import get_notification_service
from app.services.rag import get_rag_pipeline
from app.services.conformance_checker import ConformanceChecker
from app.services.llm import LLMDegradedError

# Setup logging
setup_logging()
logger = get_logger(__name__)

# ✅ SEC: KOL-142c - Rate Limiting Configuration
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import redis
from redis.exceptions import RedisError


def _init_rate_limiter() -> Limiter:
    """Initialize rate limiter with Redis backend or graceful fallback."""
    try:
        client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True,
        )
        client.ping()
        logger.info("Rate limiter using Redis backend")
        return Limiter(
            key_func=get_remote_address,
            storage_uri=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
        )
    except RedisError as e:
        logger.warning(f"Redis unavailable, using in-memory rate limiter: {e}")
        return Limiter(key_func=get_remote_address)


# Rate limiter is initialized lazily inside the FastAPI lifespan handler
limiter: Optional[Limiter] = None



@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    logger.info("Starting Kolabri AI-Engine", version="1.0.0", env=settings.ENV)

    # Ensure data directories exist
    for d in ["data/event_logs", "data/static/images"]:
        import os

        os.makedirs(d, exist_ok=True)

    # Initialize services
    vector_store = get_vector_store()
    await vector_store.initialize()

    mongo_logger = get_mongo_logger()
    await mongo_logger.connect()

    get_logic_listener()
    get_notification_service()
    if not settings.UNIFIED_PROVIDER_ENABLED:
        get_rag_pipeline()
    ConformanceChecker()

    # Initialize rate limiter (truly lazy - only runs at app startup)
    global limiter
    limiter = _init_rate_limiter()
    app.state.limiter = limiter


    yield

    # Shutdown
    logger.info("Shutting down Kolabri AI-Engine")

    await mongo_logger.close()


# Create FastAPI application
# ✅ SEC: KOL-141 - Disable docs in production
app = FastAPI(
    title="Kolabri AI-Engine",
    description="AI computation service for collaborative learning platform",
    version="1.0.0",
    docs_url="/docs"
    if (settings.ENV == "development" and settings.DOCS_ENABLED)
    else None,
    redoc_url="/redoc"
    if (settings.ENV == "development" and settings.DOCS_ENABLED)
    else None,
    openapi_url="/openapi.json" if settings.ENV == "development" else None,
    lifespan=lifespan,
)

# ✅ SEC: KOL-142c - Configure rate limiter exception handler
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.error_handlers import (
    http_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
    ExceptionMiddleware,
)

app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_middleware(ExceptionMiddleware)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.CORE_API_URL,
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# [PRIORITY 1] GZip Compression untuk response optimization
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)

# ✅ SEC: KOL-148 - Request size limit middleware
from app.middleware.request_size_limit import LimitRequestSizeMiddleware

app.add_middleware(LimitRequestSizeMiddleware, max_size_bytes=10 * 1024 * 1024)

from app.middleware.request_id import RequestIDMiddleware, REQUEST_ID_HEADER

app.add_middleware(RequestIDMiddleware)

# ✅ SEC: KOL-142 - Authentication Middleware for sensitive routes
from app.middleware.auth import require_auth
from fastapi import Depends

# Include API routes with authentication
# Protect sensitive endpoints with Depends(require_auth)
app.include_router(api_router, prefix="/api", dependencies=[Depends(require_auth)])

# Batch RAG endpoint (high-throughput path used by tests + KOL-42 harness)
from app.api.batch_routes import router as batch_router

app.include_router(batch_router, prefix="/api", dependencies=[Depends(require_auth)])


# ✅ SEC: KOL-145 - Exception Handlers for sanitized error responses
# Domain-specific handler kept here. Generic handlers live in app/core/error_handlers.py.


@app.exception_handler(LLMDegradedError)
async def llm_degraded_exception_handler(request: Request, exc: LLMDegradedError):
    """Map LLM degraded errors to HTTP 503 with structured outcome."""
    from app.core.error_handlers import _request_id_for

    request_id = _request_id_for(request)
    logger.warning(
        "llm_degraded_outcome",
        reason=exc.reason,
        retry_after=exc.retry_after,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": "DEGRADED",
            "outcome": "degraded",
            "reason": exc.reason,
            "message": "AI provider is temporarily unavailable. Please retry shortly.",
            "retry_after": exc.retry_after,
            "request_id": request_id,
        },
        headers={
            REQUEST_ID_HEADER: request_id,
            "Retry-After": str(exc.retry_after),
        },
    )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Kolabri AI-Engine",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs" if settings.DEBUG else "disabled",
    }


if __name__ == "__main__":
    workers = int(settings.WORKERS) if hasattr(settings, "WORKERS") else 1
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=1 if settings.DEBUG else workers,
        log_level=settings.LOG_LEVEL.lower(),
        limit_concurrency=100,
        timeout_keep_alive=30,
    )
