"""
Orchestration endpoint — main chat pipeline.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.core.logging import get_logger
from app.api.schemas import OrchestrationRequest, OrchestrationResponse
from app.services.orchestration import get_orchestrator

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "/chat",
    response_model=OrchestrationResponse,
    tags=["Orchestration"],
    summary="Orchestrated chat message processing",
    description="Process a student message through the full orchestration pipeline with NLP analysis, RAG, and intervention triggers.",
)
async def orchestrated_chat(request: OrchestrationRequest):
    try:
        orchestrator = get_orchestrator()
        result = await orchestrator.handle_message(
            user_id=request.user_id,
            group_id=request.group_id,
            message=request.message,
            topic=request.topic or "General Discussion",
            collection_name=request.collection_name,
            course_id=request.course_id,
            chat_room_id=request.chat_room_id,
            guardrail_policy=request.guardrail_policy,
            scaffolding_config=request.scaffolding_config,
            session_week_index=request.session_week_index,
            max_week_index=request.max_week_index,
            chat_history=request.chat_history,
        )

        return OrchestrationResponse(
            success=result.success,
            bot_response=result.reply,
            system_intervention=result.intervention,
            intervention_type=result.intervention_type,
            action_taken=result.action_taken,
            should_notify_teacher=result.should_notify_teacher,
            quality_score=result.quality_score,
            meta=result.analytics,
            guardrail_outcome=result.analytics.get("guardrail_outcome")
            if result.analytics
            else None,
            guardrail_reason=result.analytics.get("guardrail_reason")
            if result.analytics
            else None,
            scaffolding_level=result.analytics.get("scaffolding_level")
            if result.analytics
            else None,
            scaffolding_outcome=result.analytics.get("scaffolding_outcome")
            if result.analytics
            else None,
            error=result.error,
            citations=result.citations or [],
        )

    except Exception:
        logger.exception("orchestrated_chat_failed")
        return OrchestrationResponse(
            success=False,
            bot_response="Maaf, terjadi kesalahan sistem.",
            action_taken="ERROR",
            should_notify_teacher=False,
            error="Internal error",
        )
