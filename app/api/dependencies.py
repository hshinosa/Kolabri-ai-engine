"""Centralized dependency injection helpers for FastAPI route modules."""

from app.services.rag import get_rag_pipeline
from app.services.document_processor import get_document_processor
from app.services.vector_store import get_vector_store
from app.services.mongodb_logger import get_mongo_logger
from app.services.logic_listener import get_logic_listener
from app.services.llm import get_llm_service
from app.services.intervention import get_intervention_service
from app.services.orchestration import get_orchestrator

__all__ = [
    "get_rag_pipeline",
    "get_document_processor",
    "get_vector_store",
    "get_mongo_logger",
    "get_logic_listener",
    "get_llm_service",
    "get_intervention_service",
    "get_orchestrator",
]
