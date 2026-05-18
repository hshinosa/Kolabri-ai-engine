"""
Goal validation & refinement endpoints.
"""

import json

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import JSONResponse

from app.core.logging import get_logger
from app.services.orchestration import get_orchestrator

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "/goals/validate",
    tags=["Goals"],
    summary="Validate a learning goal against SMART criteria",
)
async def validate_goal(
    goal_text: str = Form(...), user_id: str = Form(...), chat_space_id: str = Form(...)
):
    try:
        orchestrator = get_orchestrator()

        result = await orchestrator.validate_goal(
            goal_text=goal_text, user_id=user_id, chat_space_id=chat_space_id
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
        logger.exception("goal_validation_api_failed", error=str(e), user_id=user_id)
        raise


@router.post(
    "/goals/refine",
    tags=["Goals"],
    summary="Get Socratic questioning hints to improve SMART goal",
)
async def get_goal_refinement(
    current_goal: str = Form(...),
    missing_criteria: str = Form(...),
):
    try:
        missing_list = json.loads(missing_criteria)

        orchestrator = get_orchestrator()

        result = await orchestrator.get_goal_refinement(
            current_goal=current_goal, missing_criteria=missing_list
        )

        logger.info(
            "goal_refinement_api",
            current_goal=current_goal[:50],
            success=result.get("success"),
        )

        return JSONResponse(content=result)

    except json.JSONDecodeError as e:
        logger.error("goal_refinement_json_error", error=str(e))
        raise HTTPException(
            status_code=400, detail="Invalid JSON format for missing_criteria"
        )
    except Exception:
        logger.exception("goal_refinement_api_failed", error=str(e))
        raise
