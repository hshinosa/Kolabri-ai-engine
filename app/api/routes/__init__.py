from fastapi import APIRouter

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

from app.api.routes.documents import (
    _process_ingest_background,
    _process_batch_file_background,
    ingest_document,
    ingest_batch,
)

from app.services.rag import get_rag_pipeline
from app.services.document_processor import get_document_processor
from app.services.vector_store import get_vector_store
from app.services.mongodb_logger import get_mongo_logger
from app.services.logic_listener import get_logic_listener
from app.services.llm import get_llm_service
from app.services.intervention import get_intervention_service
from app.services.orchestration import get_orchestrator

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

__all__ = [
    "router",
    "get_rag_pipeline",
    "get_document_processor",
    "get_vector_store",
    "get_mongo_logger",
    "get_logic_listener",
    "get_llm_service",
    "get_intervention_service",
    "get_orchestrator",
    "_process_ingest_background",
    "_process_batch_file_background",
    "ingest_document",
    "ingest_batch",
]
