"""
Goal validation & refinement endpoints.
"""

import json
from typing import Any, Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.schemas import ProviderContextV1

from app.core.config import settings
from app.core.logging import get_logger
from app.services.orchestration import get_orchestrator

logger = get_logger(__name__)

router = APIRouter()


def dump_provider_context(
    provider_context: Optional[ProviderContextV1],
) -> Optional[dict[str, Any]]:
    if provider_context is None:
        return None
    return provider_context.model_dump(exclude_none=True)


def resolve_provider_context(
    provider_context: Optional[ProviderContextV1],
) -> Optional[dict[str, Any]]:
    if not settings.UNIFIED_PROVIDER_ENABLED:
        return None
    if settings.UNIFIED_PROVIDER_GOALS:
        return dump_provider_context(provider_context)
    return dump_provider_context(provider_context)


class GoalValidateBody(BaseModel):
    goal_text: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    chat_space_id: str = Field(..., min_length=1)
    week_context: Optional[dict[str, Any]] = None
    provider_context: Optional[ProviderContextV1] = None
    group_id: Optional[str] = None

@router.post(
    "/goals/validate",
    tags=["Goals"],
    summary="Validate a learning goal against SMART criteria",
)
async def validate_goal(request: Request):
    try:
        content_type = request.headers.get("content-type", "")
        week_context = None
        provider_context = None
        if "application/json" in content_type:
            body = GoalValidateBody.model_validate(await request.json())
            goal_text = body.goal_text
            user_id = body.user_id
            chat_space_id = body.chat_space_id
            group_id = body.group_id
            week_context = body.week_context
        else:
            form = await request.form()
            goal_text = str(form.get("goal_text", ""))
            user_id = str(form.get("user_id", ""))
            chat_space_id = str(form.get("chat_space_id", ""))
            group_id = str(form.get("group_id", "")) or None
            raw_ctx = form.get("week_context")
            if raw_ctx:
                try:
                    week_context = json.loads(str(raw_ctx))
                except json.JSONDecodeError:
                    week_context = None

        orchestrator = get_orchestrator(provider_context=provider_context)
        result = await orchestrator.validate_goal(
            goal_text=goal_text,
            user_id=user_id,
            chat_space_id=chat_space_id,
            week_context=week_context,
            group_id=group_id,
        )

        logger.info(
            "goal_validation_api",
            user_id=user_id,
            chat_space_id=chat_space_id,
            is_valid=result.get("is_valid"),
            score=result.get("score"),
        )

        return JSONResponse(content=result)

    except Exception:
        logger.exception("goal_validation_api_failed")
        raise


@router.post(
    "/goals/refine",
    tags=["Goals"],
    summary="Get Socratic questioning hints to improve SMART goal",
)
async def get_goal_refinement(
    current_goal: str = Form(...),
    missing_criteria: str = Form(...),
    provider_context: Optional[str] = Form(None),
):
    try:
        missing_list = json.loads(missing_criteria)

        parsed_ctx = None
        if provider_context:
            try:
                parsed_ctx = json.loads(provider_context)
            except (json.JSONDecodeError, TypeError):
                pass
        orchestrator = get_orchestrator(provider_context=parsed_ctx)

        result = await orchestrator.get_goal_refinement(
            current_goal=current_goal, missing_criteria=missing_list
        )

        logger.info(
            "goal_refinement_api",
            current_goal=current_goal[:50],
            success=result.get("success"),
        )

        return JSONResponse(content=result)

    except json.JSONDecodeError:
        logger.exception("goal_refinement_json_error")
        raise HTTPException(
            status_code=400, detail="Invalid JSON format for missing_criteria"
        )
    except Exception:
        logger.exception("goal_refinement_api_failed")
        raise
