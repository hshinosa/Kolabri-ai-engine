"""
Kolabri AI-Engine
=================
FastAPI backend for AI computation, RAG pipeline, and LLM integration.
Uses GLM-4.7 (OpenAI Compatible) as the primary LLM provider.
"""

import uvicorn
import asyncio
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.api.routes import router as api_router
from app.services.vector_store import get_vector_store
from app.services.mongodb_logger import get_mongo_logger
from app.services.logic_listener import get_logic_listener
from app.services.notification_service import get_notification_service
from app.services.rag import get_rag_pipeline
from app.services.conformance_checker import ConformanceChecker

# Setup logging
setup_logging()
logger = get_logger(__name__)

# ✅ SEC: KOL-142c - Rate Limiting Configuration
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)


async def silence_monitor_task():
    """Background task to monitor silent groups and trigger interventions."""
    logger.info("Silence monitor background task started")
    logic_listener = get_logic_listener()
    notification_service = get_notification_service()
    
    while True:
        try:
            # Check every 60 seconds
            await asyncio.sleep(60)
            
            silent_groups = logic_listener.get_all_silent_groups()
            
            if silent_groups:
                logger.info(f"Detected {len(silent_groups)} silent groups")
                
                for group_id in silent_groups:
                    trigger = logic_listener.check_silence(group_id)
                    
                    if trigger.should_intervene:
                        # Send to Core-API
                        success = await notification_service.send_intervention(
                            group_id=group_id,
                            message=trigger.suggested_message,
                            intervention_type="silence",
                            metadata=trigger.metadata
                        )
                        
                        if success:
                            # Update timestamp so we don't spam every minute
                            # We reset the last message time to 'now' to start the 10m timer again
                            logic_listener.update_last_message_time(group_id)
            
        except asyncio.CancelledError:
            logger.info("Silence monitor task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in silence monitor task: {str(e)}")
            await asyncio.sleep(10) # Wait a bit before retry on error


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

    # Warm up safety and orchestration services so the enriched TA flow
    # is ready before the first request arrives.
    get_logic_listener()
    get_notification_service()
    get_rag_pipeline()
    ConformanceChecker()
    
    # Start background monitor
    monitor_task = asyncio.create_task(silence_monitor_task())
    
    yield
    
    # Shutdown
    logger.info("Shutting down Kolabri AI-Engine")
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass
    
    await mongo_logger.close()


# Create FastAPI application
# ✅ SEC: KOL-141 - Disable docs in production
app = FastAPI(
    title="Kolabri AI-Engine",
    description="AI computation service for collaborative learning platform",
    version="1.0.0",
    docs_url="/docs" if (settings.ENV == "development" and settings.DOCS_ENABLED) else None,
    redoc_url="/redoc" if (settings.ENV == "development" and settings.DOCS_ENABLED) else None,
    openapi_url="/openapi.json" if settings.ENV == "development" else None,
    lifespan=lifespan,
)

# ✅ SEC: KOL-142c - Configure rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
app.add_middleware(LimitRequestSizeMiddleware, max_size_bytes=10*1024*1024)

# ✅ SEC: KOL-142 - Authentication Middleware for sensitive routes
from app.middleware.auth import require_auth
from fastapi import Depends

# Include API routes with authentication
# Protect sensitive endpoints with Depends(require_auth)
app.include_router(api_router, prefix="/api", dependencies=[Depends(require_auth)])


# ✅ SEC: KOL-145 - Exception Handlers for sanitized error responses
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions with sanitized response."""
    logger.error(
        "Unhandled exception",
        exc_info=exc,
        path=request.url.path,
        method=request.method
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "INTERNAL_SERVER_ERROR",
            "message": "An internal error occurred. Please try again later."
        }
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with sanitized response."""
    logger.warning(
        "HTTP exception",
        status_code=exc.status_code,
        detail=str(exc.detail),
        path=request.url.path
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": "REQUEST_ERROR",
            "message": str(exc.detail) if exc.status_code < 500 else "An error occurred"
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with sanitized response."""
    logger.warning(
        "Validation error",
        errors=str(exc.errors()),
        path=request.url.path
    )
    return JSONResponse(
        status_code=422,
        content={
            "detail": "VALIDATION_ERROR",
            "message": "Invalid request data. Please check your input."
        }
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
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
