from __future__ import annotations

from datetime import datetime
from typing import Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.schemas import HealthResponse
from app.core.config import settings
from app.core.logging import get_logger
from app.services.reranker import get_reranker
from app.services.vector_store import get_vector_store

logger = get_logger(__name__)

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Health check endpoint",
)
async def health_check():
    services = {"vector_store": False, "llm": False}
    dependencies: Dict[str, str] = {
        "mongo": "down",
        "redis": "down",
        "vector_store": "down",
        "llm": "down",
    }

    try:
        vector_store = get_vector_store()
        await vector_store._ensure_collection("health_check")
        services["vector_store"] = True
        dependencies["vector_store"] = "healthy"
    except Exception:
        logger.exception("health_check_vector_store_failed")

    try:
        from app.services.llm import get_llm_service
        from app.core.config import settings

        # Always resolve the service; in unified (lazy) mode force provider
        # resolution so /health reports reality instead of the flag.
        llm = get_llm_service()
        if settings.UNIFIED_PROVIDER_ENABLED and llm.model is None:
            await llm.ensure_ready()
        services["llm"] = llm.model is not None
        dependencies["llm"] = "healthy" if services["llm"] else "down"
    except Exception:
        logger.exception("health_check_llm_failed")

    try:
        from app.services.mongodb_logger import get_mongo_logger

        mongo = get_mongo_logger()
        if not mongo.enabled:
            dependencies["mongo"] = "healthy"
        elif await mongo.ping():
            dependencies["mongo"] = "healthy"
    except Exception:
        logger.exception("health_check_mongo_failed")

    try:
        from app.core.redis_cache import get_redis_cache

        redis_cache = await get_redis_cache()
        if await redis_cache.ping():
            dependencies["redis"] = "healthy"
    except Exception:
        logger.exception("health_check_redis_failed")

    circuit_breakers: Dict[str, str] = {}
    try:
        from app.services.circuit_breaker import get_llm_circuit_breaker

        breaker = get_llm_circuit_breaker()
        circuit_breakers["llm"] = breaker.state.value
    except Exception:
        logger.exception("health_check_breaker_failed")

    is_degraded = any(state != "healthy" for state in dependencies.values()) or any(
        state == "open" for state in circuit_breakers.values()
    )
    overall_status = "degraded" if is_degraded else "healthy"

    reranker = get_reranker()
    body = HealthResponse(
        status=overall_status,
        version=settings.VERSION,
        timestamp=datetime.now(),
        services=services,
        reranker_enabled=reranker.enabled,
        dependencies=dependencies,
        circuit_breakers=circuit_breakers,
    )
    if is_degraded:
        return JSONResponse(status_code=503, content=body.model_dump(mode="json"))
    return body
