"""
Monitoring & health endpoints.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from app.core.logging import get_logger
from app.services.circuit_breaker import get_llm_circuit_breaker
from app.services.monitoring import get_monitor
from app.services.reranker import get_reranker

logger = get_logger(__name__)

router = APIRouter()


@router.get("/metrics", tags=["Monitoring"])
async def metrics():
    """
    Prometheus metrics endpoint.
    
    Returns all performance metrics in Prometheus format.
    """
    try:
        monitor = get_monitor()
        return Response(
            content=monitor.get_metrics(),
            media_type=monitor.get_content_type()
        )
    except Exception:
        logger.exception("metrics_endpoint_failed")
        raise


@router.get("/health/monitoring", tags=["Monitoring"])
async def get_monitoring_status():
    """Get monitoring service status and dashboard data."""
    try:
        monitor = get_monitor()
        return JSONResponse(content=monitor.get_dashboard_data())
    except Exception:
        logger.exception("monitoring_status_failed")
        raise


@router.get("/health/circuit-breakers", tags=["Monitoring"])
async def get_circuit_breaker_status():
    """Get status of all circuit breakers."""
    try:
        llm_cb = get_llm_circuit_breaker()
        return JSONResponse(content={
            "llm_service": llm_cb.get_metrics()
        })
    except Exception:
        logger.exception("circuit_breaker_status_failed")
        raise


@router.get("/health/reranker", tags=["Monitoring"])
async def get_reranker_status():
    """Get reranker health and metrics."""
    try:
        reranker = get_reranker()
        return JSONResponse(content=reranker.get_metrics())
    except Exception:
        logger.exception("reranker_status_failed")
        raise
