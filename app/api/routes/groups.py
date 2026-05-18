"""
Group monitoring & Logic Listener endpoints.
"""

from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Query
from fastapi.responses import JSONResponse

from app.core.logging import get_logger
from app.services.orchestration import get_orchestrator

logger = get_logger(__name__)

router = APIRouter()


@router.get(
    "/groups/{group_id}/status",
    tags=["Groups"],
    summary="Check group status using Logic Listener",
)
async def check_group_status(
    group_id: str, topic: Optional[str] = Query(None, description="Discussion topic")
):
    try:
        orchestrator = get_orchestrator()

        result = await orchestrator.check_group_status(group_id=group_id, topic=topic)

        logger.info(
            "group_status_check_api",
            group_id=group_id,
            should_intervene=result.get("should_intervene"),
            interventions_count=len(result.get("interventions", [])),
        )

        return JSONResponse(content=result)

    except Exception:
        logger.exception("group_status_check_api_failed", group_id=group_id)
        raise


@router.post(
    "/groups/{group_id}/track-participation",
    tags=["Groups"],
    summary="Track user participation for Logic Listener",
)
async def track_participation(group_id: str, user_id: str = Form(...)):
    try:
        orchestrator = get_orchestrator()

        result = await orchestrator.track_participation(
            group_id=group_id, user_id=user_id
        )

        logger.info("participation_tracking_api", group_id=group_id, user_id=user_id)

        return JSONResponse(content=result)

    except Exception:
        logger.exception("participation_tracking_api_failed",
            group_id=group_id,
            user_id=user_id)
        raise


@router.post(
    "/groups/{group_id}/update-last-message",
    tags=["Groups"],
    summary="Update last message timestamp for Logic Listener",
)
async def update_last_message_time(group_id: str):
    try:
        orchestrator = get_orchestrator()

        result = await orchestrator.update_last_message_time(group_id=group_id)

        logger.info("last_message_time_update_api", group_id=group_id)

        return JSONResponse(content=result)

    except Exception:
        logger.exception("last_message_time_update_api_failed", group_id=group_id)
        raise


@router.post(
    "/groups/{group_id}/set-topic",
    tags=["Groups"],
    summary="Set the topic for a group for Logic Listener",
)
async def set_group_topic(group_id: str, topic: str = Form(...)):
    try:
        orchestrator = get_orchestrator()

        result = await orchestrator.set_group_topic(group_id=group_id, topic=topic)

        logger.info("group_topic_set_api", group_id=group_id, topic=topic)

        return JSONResponse(content=result)

    except Exception:
        logger.exception("group_topic_set_api_failed", group_id=group_id, topic=topic)
        raise
