"""
Orchestration endpoint — main chat pipeline.
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import json as _json

from app.core.config import settings
from app.core.logging import get_logger
from app.api.schemas import OrchestrationRequest
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
    return dump_provider_context(provider_context)


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
                week_context=request.week_context,
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
