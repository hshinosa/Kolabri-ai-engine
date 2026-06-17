"""
Intervention endpoints — analyze, summary, prompt.
"""

from fastapi import APIRouter, HTTPException

from app.core.config import settings
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


def dump_provider_context(provider_context):
    if provider_context is None:
        return None
    return provider_context.model_dump(exclude_none=True)


def resolve_provider_context(provider_context, feature_flag: bool):
    if not settings.UNIFIED_PROVIDER_ENABLED:
        return None
    if feature_flag:
        return dump_provider_context(provider_context)
    return dump_provider_context(provider_context)


@router.post(
    "/intervention/analyze",
    response_model=InterventionResponse,
    tags=["Intervention"],
    summary="Analyze chat for intervention needs",
    description="Analyze a group chat conversation and determine if AI intervention is needed.",
)
async def analyze_intervention(request: InterventionRequest):
    try:
        intervention_service = get_intervention_service(
            provider_context=resolve_provider_context(
                request.provider_context,
                settings.UNIFIED_PROVIDER_INTERVENTIONS,
            )
        )

        messages_dicts = [
            {
                "sender": msg.sender,
                "content": msg.content,
                "timestamp": msg.timestamp,
                "sender_id": msg.sender_id,
            }
            for msg in request.messages
        ]

        result = await intervention_service.analyze_and_intervene(
            messages=messages_dicts,
            topic=request.topic,
            chat_room_id=request.chat_room_id,
        )

        intervention_type_value = (
            result.intervention_type.value
            if result.intervention_type is not None
            else ""
        )

        return InterventionResponse(
            success=result.success,
            should_intervene=result.should_intervene,
            message=result.message or "",
            intervention_type=intervention_type_value,
            confidence=result.confidence or 0.0,
            reason=result.reason or "",
            error=result.error,
        )

    except Exception:
        logger.exception("intervention_analysis_failed")
        return InterventionResponse(
            success=False,
            should_intervene=False,
            message="",
            intervention_type="",
            confidence=0.0,
            reason="Internal error",
            error="Internal error",
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
        intervention_service = get_intervention_service(
            provider_context=resolve_provider_context(
                request.provider_context,
                settings.UNIFIED_PROVIDER_SUMMARIES,
            )
        )

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

    except Exception:
        logger.exception("summary_generation_failed")
        return SummaryResponse(
            success=False,
            summary="",
            message_count=len(request.messages),
            error="Internal error",
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
        intervention_service = get_intervention_service(
            provider_context=resolve_provider_context(
                request.provider_context,
                settings.UNIFIED_PROVIDER_INTERVENTIONS,
            )
        )

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

    except Exception:
        logger.exception("prompt_generation_failed")
        return PromptResponse(
            success=False,
            prompt="",
            topic=request.topic,
            error="Internal error",
        )
