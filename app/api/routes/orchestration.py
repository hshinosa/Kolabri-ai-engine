"""
Orchestration endpoint — main chat pipeline.
"""

import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
import json as _json

from app.core.config import settings
from app.core.logging import get_logger
from app.api.schemas import OrchestrationRequest, OrchestrationResponse
from app.services.orchestration import get_orchestrator

logger = get_logger(__name__)

router = APIRouter()


def dump_provider_context(provider_context):
    if provider_context is None:
        return None
    return provider_context.model_dump(exclude_none=True)


def resolve_provider_context(provider_context):
    if not settings.UNIFIED_PROVIDER_ENABLED:
        return None
    if settings.UNIFIED_PROVIDER_ORCHESTRATION:
        return dump_provider_context(provider_context)
    return dump_provider_context(provider_context)


@router.post(
    "/chat",
    response_model=OrchestrationResponse,
    tags=["Orchestration"],
    summary="Orchestrated chat message processing",
    description="Process a student message through the full orchestration pipeline with NLP analysis, RAG, and intervention triggers.",
)

async def orchestrated_chat(request: OrchestrationRequest):
    try:
        orchestrator = get_orchestrator(
            provider_context=resolve_provider_context(request.provider_context)
        )
        # PERF-AI-08: End-to-end request timeout (60s) for fast-fail
        result = await asyncio.wait_for(
            orchestrator.handle_message(
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
            ),
            timeout=60.0,
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

    except asyncio.TimeoutError:
        logger.warning("orchestrated_chat_timeout", timeout=60.0)
        return OrchestrationResponse(
            success=False,
            bot_response="Maaf, respons terlalu lama. Silakan coba lagi.",
            action_taken="TIMEOUT",
            should_notify_teacher=False,
            error="Request timeout (60s)",
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


@router.post(
    "/chat/stream",
    tags=["Orchestration"],
    summary="Orchestrated chat with SSE streaming (NO_FETCH path)",
    description="Stream orchestrated chat responses. NO_FETCH path (greetings, short follow-ups) streams tokens; FETCH path returns full result.",
)
async def orchestrated_chat_stream(request: OrchestrationRequest):
    orchestrator = get_orchestrator(
        provider_context=resolve_provider_context(request.provider_context)
    )

    async def event_generator():
        try:
            async for event in orchestrator.handle_message_stream(
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
            ):
                yield f"data: {_json.dumps(event, default=str)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            logger.exception("orchestrated_chat_stream_failed")
            yield f"data: {_json.dumps({'type': 'error', 'content': 'Internal error'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
