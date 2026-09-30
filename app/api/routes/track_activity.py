from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas import TrackActivityRequest, TrackActivityResponse
from app.services.logic_listener import get_logic_listener

router = APIRouter()


@router.post(
    "/track-activity",
    response_model=TrackActivityResponse,
    tags=["Analytics"],
    summary="Track group activity for Logic Listener silence detection",
)
async def track_activity(request: TrackActivityRequest):
    logic_listener = get_logic_listener()
    await logic_listener.update_last_message_time(request.group_id)
    if request.user_id:
        await logic_listener.track_participation(request.group_id, request.user_id)
    return {"success": True}
