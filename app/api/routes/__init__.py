from fastapi import APIRouter

from app.core.config import settings

from app.api.routes.health import router as _health_router
from app.api.routes.track_activity import router as _track_activity_router
from app.api.routes.monitoring import router as _monitoring_router
from app.api.routes.goals import router as _goals_router
from app.api.routes.groups import router as _groups_router
from app.api.routes.efficiency import router as _efficiency_router
from app.api.routes.analytics import router as _analytics_router
from app.api.routes.orchestration import router as _orchestration_router
from app.api.routes.interventions import router as _interventions_router
from app.api.routes.documents import router as _documents_router
from app.api.routes.chat import router as _chat_router
from app.api.routes.discussion_direction import router as _discussion_direction_router

from app.api.routes.documents import (
    _process_ingest_background,
    _process_batch_file_background,
    ingest_document,
    ingest_batch,
)

router = APIRouter()
router.include_router(_health_router)
router.include_router(_track_activity_router)
router.include_router(_documents_router)
router.include_router(_chat_router)
router.include_router(_analytics_router)
router.include_router(_goals_router)
router.include_router(_groups_router)
router.include_router(_efficiency_router)
router.include_router(_monitoring_router)
router.include_router(_orchestration_router)
router.include_router(_interventions_router)
router.include_router(_discussion_direction_router)

__all__ = [
    "router",
    "settings",
    "_process_ingest_background",
    "_process_batch_file_background",
    "ingest_document",
    "ingest_batch",
]
