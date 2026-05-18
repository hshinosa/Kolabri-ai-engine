"""
Analytics, dashboard & CSV export endpoints.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from app.core.logging import get_logger
from app.api.schemas import (
    EngagementAnalysisRequest,
    EngagementAnalysisResponse,
    GroupAnalyticsResponse,
)
from app.services.export_service import get_export_service
from app.services.mongodb_logger import get_mongo_logger
from app.services.nlp_analytics import get_engagement_analyzer
from app.services.orchestration import get_orchestrator

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "/analytics/engagement",
    response_model=EngagementAnalysisResponse,
    tags=["Analytics"],
    summary="Analyze text engagement metrics (Core-API Proxy)",
)
async def analyze_engagement(request: EngagementAnalysisRequest):
    try:
        analyzer = get_engagement_analyzer()
        analysis = analyzer.analyze_interaction(request.text)

        return EngagementAnalysisResponse(
            success=True,
            lexical_variety=analysis.lexical_variety,
            engagement_type=analysis.engagement_type.value,
            is_higher_order=analysis.is_higher_order,
            hot_indicators=analysis.hot_indicators,
            word_count=len(request.text.split()),
            unique_words=len(set(request.text.lower().split())),
            confidence=1.0,
        )
    except Exception as e:
        logger.error("engagement_analysis_failed", error=str(e))
        return EngagementAnalysisResponse(
            success=False,
            error=str(e),
            lexical_variety=0,
            engagement_type="unknown",
            is_higher_order=False,
            hot_indicators=[],
            word_count=0,
            unique_words=0,
            confidence=0,
        )


@router.get(
    "/analytics/dashboard/group/{group_id}",
    tags=["Analytics"],
    summary="Get dashboard data for a GROUP (Collaboration & Dynamics)",
)
async def get_group_dashboard(group_id: str):
    try:
        orchestrator = get_orchestrator()
        data = await orchestrator.get_group_dashboard_data(group_id)
        return JSONResponse(content=data)
    except Exception as e:
        logger.error("group_dashboard_api_failed", group_id=group_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/analytics/dashboard/individual/{user_id}",
    tags=["Analytics"],
    summary="Get dashboard data for an INDIVIDUAL student",
)
async def get_individual_dashboard(user_id: str):
    try:
        orchestrator = get_orchestrator()
        data = await orchestrator.get_individual_dashboard_data(user_id)
        return JSONResponse(content=data)
    except Exception as e:
        logger.error("individual_dashboard_api_failed", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/analytics/dashboard/{group_id}",
    tags=["Analytics"],
    summary="Get unified dashboard data (Legacy - redirects to group)",
)
async def get_dashboard_data_legacy(group_id: str):
    return await get_group_dashboard(group_id)


@router.get(
    "/export/activity/group/{group_id}",
    tags=["Analytics"],
    summary="Export group activity data to CSV (Student Breakdown)",
)
async def export_group_activity_csv(group_id: str):
    try:
        export_service = get_export_service()
        csv_data = await export_service.export_group_activity_detailed(group_id)

        filename = f"student_breakdown_{group_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        logger.error("csv_export_failed", group_id=group_id, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to export activity data: {str(e)}"
        )


@router.get(
    "/export/activity/chat-space/{chat_space_id}",
    tags=["Analytics"],
    summary="Export chat space activity data to CSV",
)
async def export_chat_space_activity_csv(
    chat_space_id: str,
    include_detailed: bool = Query(True, description="Include detailed metrics"),
):
    try:
        export_service = get_export_service()

        csv_data = await export_service.export_chat_space_activity(
            chat_space_id=chat_space_id, include_detailed=include_detailed
        )

        filename = f"activity_session_{chat_space_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        logger.info(
            "activity_csv_exported",
            chat_space_id=chat_space_id,
            size_bytes=len(csv_data),
            detailed=include_detailed,
        )

        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        logger.error("csv_export_failed", chat_space_id=chat_space_id, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to export activity data: {str(e)}"
        )


@router.get(
    "/export/process-mining/case/{case_id}",
    tags=["Analytics"],
    summary="Export raw event logs to CSV for Process Mining (XES compatible)",
)
async def export_process_mining_csv(case_id: str):
    try:
        from app.services.mongodb_logger import get_mongo_logger as _get_mongo
        mongo_logger = _get_mongo()

        csv_data = await mongo_logger.export_to_csv(case_id=case_id)

        filename = (
            f"process_mining_{case_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )

        logger.info(
            "process_mining_csv_exported", case_id=case_id, size_bytes=len(csv_data)
        )

        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        logger.error("process_mining_export_failed", case_id=case_id, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to export process mining data: {str(e)}"
        )


@router.get(
    "/analytics/group/{group_id}",
    response_model=GroupAnalyticsResponse,
    tags=["Analytics"],
    summary="Get group analytics (alias)",
)
async def get_group_analytics_alias(group_id: str):
    try:
        orchestrator = get_orchestrator()
        data = await orchestrator.get_group_dashboard_data(group_id)

        return GroupAnalyticsResponse(
            success=True,
            group_id=group_id,
            message_count=data.get("message_count", 0),
            quality_score=data.get("quality_score"),
            quality_breakdown=data.get("quality_breakdown") or {},
            recommendation=data.get("recommendation"),
            participants=data.get("participants") or [],
            participant_count=data.get("participant_count", 0),
            engagement_distribution=data.get("engagement_distribution") or {},
            hot_percentage=data.get("hot_percentage"),
        )

    except Exception as e:
        logger.error("group_analytics_alias_failed", error=str(e), group_id=group_id)
        return GroupAnalyticsResponse(
            success=False,
            group_id=group_id,
            error=str(e),
        )


@router.get(
    "/analytics/export",
    tags=["Analytics"],
    summary="Export process mining data (general)",
)
async def export_process_mining_general(
    format: Optional[str] = Query(None, description="Response format: 'csv' for raw file, default is JSON metadata"),
):
    try:
        mongo_logger = get_mongo_logger()
        csv_data = await mongo_logger.export_to_csv()

        lines = csv_data.strip().split("\n") if csv_data.strip() else []
        total_events = max(0, len(lines) - 1)

        unique_cases = 0
        if total_events > 0:
            case_ids = set()
            for line in lines[1:]:
                parts = line.split(",")
                if parts:
                    case_ids.add(parts[0])
            unique_cases = len(case_ids)

        if format == "csv":
            filename = f"process_mining_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            logger.info("process_mining_general_export_csv", size_bytes=len(csv_data))
            return Response(
                content=csv_data,
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )

        logger.info(
            "process_mining_general_export_json",
            total_events=total_events,
            unique_cases=unique_cases,
        )
        return JSONResponse(
            content={
                "success": True,
                "file_url": "/api/analytics/export?format=csv",
                "total_events": total_events,
                "unique_cases": unique_cases,
                "message": f"Export ready: {total_events} events across {unique_cases} cases",
            }
        )

    except Exception as e:
        logger.error("process_mining_general_export_failed", error=str(e))
        return JSONResponse(
            content={
                "success": False,
                "file_url": "",
                "total_events": 0,
                "unique_cases": 0,
                "error": str(e),
            }
        )
