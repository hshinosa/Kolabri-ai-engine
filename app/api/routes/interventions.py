"""
Intervention endpoints — analyze, summary, prompt.
"""

from fastapi import APIRouter, HTTPException

from app.core.logging import get_logger
from app.api.schemas import (
    InterventionRequest,
    InterventionResponse,
    SummaryRequest,
    SummaryResponse,
    PromptRequest,
    PromptResponse,
)
from app.services.intervention import get_intervention_service

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "/intervention/analyze",
    response_model=InterventionResponse,
    tags=["Intervention"],
    summary="Analyze chat for intervention needs",
    description="Analyze a group chat conversation and determine if AI intervention is needed.",
)
async def analyze_intervention(request: InterventionRequest):
    try:
        intervention_service = get_intervention_service()

        messages_dicts = [
            {
                "sender": msg.sender,
                "content": msg.content,
                "timestamp": msg.timestamp,
                "sender_id": msg.sender_id,
            }
            for msg in request.messages
        ]

        result = await intervention_service.analyze_conversation(
            messages=messages_dicts,
            group_id=request.group_id,
            topic=request.topic,
        )

        return InterventionResponse(
            success=result.success,
            needs_intervention=result.needs_intervention,
            intervention_type=result.intervention_type.value
            if result.intervention_type
            else None,
            message=result.message,
            confidence=result.confidence,
            error=result.error,
        )

    except Exception as e:
        logger.error("intervention_analysis_failed", error=str(e))
        return InterventionResponse(
            success=False,
            needs_intervention=False,
            error=str(e),
        )


@router.post(
    "/intervention/summary",
    response_model=SummaryResponse,
    tags=["Intervention"],
    summary="Generate discussion summary",
    description="Generate a summary of a group chat discussion with optional action items.",
)
async def generate_summary(request: SummaryRequest):
    try:
        intervention_service = get_intervention_service()

        messages_dicts = [
            {
                "sender": msg.sender,
                "content": msg.content,
                "timestamp": msg.timestamp,
                "sender_id": msg.sender_id,
            }
            for msg in request.messages
        ]

        result = await intervention_service.generate_summary(
            messages=messages_dicts,
            chat_room_id=request.chat_room_id,
        )

        return SummaryResponse(
            success=result.success,
            summary=result.message,
            message_count=len(request.messages),
            error=result.error,
        )

    except Exception as e:
        logger.error("summary_generation_failed", error=str(e))
        return SummaryResponse(
            success=False,
            summary="",
            message_count=len(request.messages),
            error=str(e),
        )


@router.post(
    "/intervention/prompt",
    response_model=PromptResponse,
    tags=["Intervention"],
    summary="Generate discussion prompt",
    description="Generate a discussion prompt for a given topic to stimulate student engagement.",
)
async def generate_prompt(request: PromptRequest):
    try:
        intervention_service = get_intervention_service()

        result = await intervention_service.generate_discussion_prompt(
            topic=request.topic,
            context=request.context,
            difficulty=request.difficulty,
        )

        return PromptResponse(
            success=result.success,
            prompt=result.message,
            topic=request.topic,
            error=result.error,
        )

    except Exception as e:
        logger.error("prompt_generation_failed", error=str(e))
        return PromptResponse(
            success=False,
            prompt="",
            topic=request.topic,
            error=str(e),
        )
