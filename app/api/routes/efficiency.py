"""
Efficiency Guard endpoints — caching, rate limiting, performance stats.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import get_logger
from app.services.efficiency_guard import get_efficiency_guard

logger = get_logger(__name__)

router = APIRouter()


@router.get(
    "/efficiency/cache/statistics",
    tags=["Efficiency"],
    summary="Get cache performance statistics",
)
async def get_cache_statistics():
    try:
        if not settings.ENABLE_EFFICIENCY_GUARD:
            return JSONResponse(
                content={"enabled": False, "message": "Efficiency Guard is disabled"}
            )

        efficiency_guard = get_efficiency_guard()
        stats = efficiency_guard.get_cache_statistics()

        logger.info(
            "cache_statistics_api",
            cache_hits=stats.get("cache_hits"),
            cache_misses=stats.get("cache_misses"),
            hit_rate=stats.get("hit_rate_percent"),
        )

        return JSONResponse(content={"enabled": True, **stats})

    except Exception:
        logger.exception("cache_statistics_api_failed", error=str(e))
        raise


@router.get(
    "/efficiency/cache/clear", tags=["Efficiency"], summary="Clear all cached responses"
)
async def clear_cache():
    try:
        if not settings.ENABLE_EFFICIENCY_GUARD:
            return JSONResponse(
                content={"enabled": False, "message": "Efficiency Guard is disabled"}
            )

        efficiency_guard = get_efficiency_guard()
        efficiency_guard.clear_cache()

        logger.info("cache_cleared_api")

        return JSONResponse(
            content={"success": True, "message": "Cache cleared successfully"}
        )

    except Exception:
        logger.exception("cache_clear_api_failed")
        raise


@router.get(
    "/efficiency/statistics",
    tags=["Efficiency"],
    summary="Get comprehensive efficiency guard statistics",
)
async def get_efficiency_statistics():
    try:
        if not settings.ENABLE_EFFICIENCY_GUARD:
            return JSONResponse(
                content={"enabled": False, "message": "Efficiency Guard is disabled"}
            )

        efficiency_guard = get_efficiency_guard()
        stats = efficiency_guard.get_statistics()

        logger.info(
            "efficiency_statistics_api",
            total_requests=stats.get("rate_limit", {}).get("total_requests"),
            cache_hit_rate=stats.get("performance", {}).get("cache_hit_rate_percent"),
        )

        return JSONResponse(content={"enabled": True, **stats})

    except Exception:
        logger.exception("efficiency_statistics_api_failed", error=str(e))
        raise


@router.get(
    "/efficiency/rate-limit/{identifier}",
    tags=["Efficiency"],
    summary="Get rate limit information for an identifier",
)
async def get_rate_limit_info(identifier: str):
    try:
        if not settings.ENABLE_EFFICIENCY_GUARD:
            return JSONResponse(
                content={"enabled": False, "message": "Efficiency Guard is disabled"}
            )

        efficiency_guard = get_efficiency_guard()
        info = efficiency_guard.get_rate_limit_info(identifier)

        logger.info(
            "rate_limit_info_api",
            identifier=identifier,
            remaining=info.get("remaining_requests"),
            is_allowed=info.get("is_allowed"),
        )

        return JSONResponse(content={"enabled": True, **info})

    except Exception:
        logger.exception("rate_limit_info_api_failed", error=str(e), identifier=identifier)
        raise


@router.get(
    "/efficiency/high-frequency-queries",
    tags=["Efficiency"],
    summary="Get most frequently executed queries",
)
async def get_high_frequency_queries(
    limit: int = Query(10, description="Maximum number of queries to return"),
):
    try:
        if not settings.ENABLE_EFFICIENCY_GUARD:
            return JSONResponse(
                content={"enabled": False, "message": "Efficiency Guard is disabled"}
            )

        efficiency_guard = get_efficiency_guard()
        queries = efficiency_guard.get_high_frequency_queries(limit=limit)

        logger.info("high_frequency_queries_api", limit=limit, count=len(queries))

        return JSONResponse(content={"enabled": True, "queries": queries})

    except Exception:
        logger.exception("high_frequency_queries_api_failed", error=str(e))
        raise
