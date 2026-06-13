"""
API Request/Response Schemas - MVP Phase 1-1.5
Kolabri AI Engine

Pydantic models for API validation.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
import re


# ============== Health Check ==============


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str
    timestamp: datetime
    services: Dict[str, bool]
    reranker_enabled: bool = False
    dependencies: Dict[str, str] = {}
    circuit_breakers: Dict[str, str] = {}


# ============== PDF Upload ==============


class PDFUploadResponse(BaseModel):
    """Response after PDF upload and processing."""

    success: bool
    message: str
    document_id: Optional[str] = None
    filename: Optional[str] = None
    chunks_created: int = 0
    processing_time_ms: float = 0
    error: Optional[str] = None


class DocumentProcessResult(BaseModel):
    """Result of processing a single document."""

    filename: str
    file_type: str
    chunks_created: int = 0
    page_count: int = 0
    image_count: int = 0
    total_characters: int = 0
    processing_time_ms: float = 0
    success: bool
    error: Optional[str] = None


class BatchUploadResponse(BaseModel):
    """Response after batch document upload (ZIP or multiple files)."""

    success: bool
    message: str
    total_files: int = 0
    successful_files: int = 0
    failed_files: int = 0
    total_chunks: int = 0
    documents: List[DocumentProcessResult] = []
    processing_time_ms: float = 0
    error: Optional[str] = None


class IngestResponse(BaseModel):
    """Response from /ingest endpoint (Core-API integration)."""

    success: bool
    message: str
    file_id: str
    document_id: str
    chunks_created: int = 0
    page_count: int = 0
    image_count: int = 0
    file_type: str = "unknown"
    processing_time_ms: float = 0
    error: Optional[str] = None


class DocumentInfo(BaseModel):
    """Information about an uploaded document."""

    document_id: str
    filename: str
    course_id: Optional[str] = None
    upload_time: datetime
    chunks_count: int
    status: str


class DocumentListResponse(BaseModel):
    """Response with list of documents."""

    success: bool
    documents: List[DocumentInfo]
    total: int


# ============== RAG Query ==============


class QueryRequest(BaseModel):
    """Request for RAG query."""

    query: str = Field(..., min_length=1, max_length=2000)
    course_id: Optional[str] = Field(None, max_length=64)
    chat_room_id: Optional[str] = Field(None, max_length=64)
    n_results: int = Field(default=5, ge=1, le=20)
    include_sources: bool = True

    @field_validator("course_id", "chat_room_id")
    @classmethod
    def validate_no_path_traversal(cls, v: Optional[str]) -> Optional[str]:
        if v and any(char in v for char in ["..", "/", "\\"]):
            raise ValueError("ID tidak boleh mengandung karakter path traversal")
        return v


class AskRequest(BaseModel):
    """Request for /ask endpoint (Core-API integration)."""

    query: str = Field(..., min_length=1, max_length=2000)
    course_id: str = Field(..., min_length=1, max_length=64)
    user_name: Optional[str] = Field(None, max_length=100)
    chat_space_id: Optional[str] = Field(None, max_length=64)
    guardrail_policy: Optional[dict[str, Any]] = None
    scaffolding_config: Optional[dict[str, Any]] = None

    @field_validator("course_id", "chat_space_id")
    @classmethod
    def validate_no_path_traversal(cls, v: Optional[str]) -> Optional[str]:
        if v and any(char in v for char in ["..", "/", "\\"]):
            raise ValueError("ID tidak boleh mengandung karakter path traversal")
        return v


class AskResponse(BaseModel):
    """Response from /ask endpoint."""

    answer: str
    success: bool = True
    error: Optional[str] = None


class ReadingRecommendationRequest(BaseModel):
    """Request for structured reading recommendations."""

    topic: str = Field(..., min_length=1, max_length=200)
    course_id: str = Field(..., min_length=1, max_length=64)
    limit: int = Field(default=3, ge=1, le=5)

    @field_validator("course_id")
    @classmethod
    def validate_course_id_no_path_traversal(cls, v: str) -> str:
        if any(char in v for char in ["..", "/", "\\"]):
            raise ValueError("ID tidak boleh mengandung karakter path traversal")
        return v


class ReadingRecommendationItem(BaseModel):
    source_title: str
    snippet: str
    rationale: str
    suggested_action: str
    page: Optional[int] = None
    relevance_score: float = 0


class ReadingRecommendationFallback(BaseModel):
    message: str
    suggestedNextStep: str


class ReadingRecommendationResponse(BaseModel):
    success: bool
    recommendations: List[ReadingRecommendationItem] = []
    fallback: Optional[ReadingRecommendationFallback] = None
    error: Optional[str] = None


class SourceInfo(BaseModel):
    """Information about a source document."""

    source: str
    page: Optional[int] = None
    chunk_index: Optional[int] = None
    relevance_score: float = 0


class QueryResponse(BaseModel):
    """Response from RAG query."""

    success: bool
    answer: str
    sources: List[SourceInfo] = []
    query: str
    tokens_used: int = 0
    processing_time_ms: float = 0
    error: Optional[str] = None


# ============== Chat Intervention ==============


class ChatMessage(BaseModel):
    """A chat message for intervention analysis."""

    sender: str
    content: str
    timestamp: Optional[datetime] = None
    sender_id: Optional[str] = None


class InterventionRequest(BaseModel):
    """Request for chat intervention."""

    messages: List[ChatMessage]
    topic: str
    chat_room_id: str
    intervention_type: Optional[str] = None  # redirect, prompt, summarize
    force: bool = False  # Force intervention even if not needed


class InterventionResponse(BaseModel):
    """Response with intervention message."""

    success: bool
    should_intervene: bool
    message: str
    intervention_type: str
    confidence: float
    reason: str
    error: Optional[str] = None


class SummaryRequest(BaseModel):
    """Request for discussion summary."""

    messages: List[ChatMessage]
    chat_room_id: str
    include_action_items: bool = True


class SummaryResponse(BaseModel):
    """Response with discussion summary."""

    success: bool
    summary: str
    message_count: int
    error: Optional[str] = None


class PromptRequest(BaseModel):
    """Request for discussion prompt generation."""

    topic: str
    context: Optional[str] = None
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")


class PromptResponse(BaseModel):
    """Response with generated prompt."""

    success: bool
    prompt: str
    topic: str
    error: Optional[str] = None


# ============== Collection Management ==============


class CreateCollectionRequest(BaseModel):
    """Request to create a new collection."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    course_id: Optional[str] = None


class CollectionResponse(BaseModel):
    """Response about a collection."""

    success: bool
    name: str
    document_count: int = 0
    message: Optional[str] = None
    error: Optional[str] = None


class CollectionListResponse(BaseModel):
    """Response with list of collections."""

    success: bool
    collections: List[Dict[str, Any]]
    total: int


# ============== Error Response ==============


class ErrorResponse(BaseModel):
    """Standard error response."""

    success: bool = False
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


# ============== Orchestration (Teacher-AI Complementarity) ==============


class ChatHistoryItem(BaseModel):
    """A message in the conversation history for context."""

    role: str  # 'user' or 'assistant'
    content: str


class OrchestrationRequest(BaseModel):
    """Request for orchestrated message handling."""

    user_id: str = Field(..., min_length=1, max_length=64)
    group_id: str = Field(..., min_length=1, max_length=64)
    message: str = Field(..., min_length=1, max_length=5000)
    topic: Optional[str] = Field(None, max_length=200)
    collection_name: Optional[str] = Field(None, max_length=100)
    course_id: Optional[str] = Field(None, max_length=64)
    chat_room_id: Optional[str] = Field(None, max_length=64)
    guardrail_policy: Optional[dict[str, Any]] = None
    scaffolding_config: Optional[dict[str, Any]] = None
    session_week_index: Optional[int] = Field(None, ge=1)
    max_week_index: Optional[int] = Field(None, ge=1)
    week_context: Optional[dict[str, Any]] = None
    chat_history: Optional[List[ChatHistoryItem]] = Field(None, max_length=20)

    @field_validator(
        "user_id", "group_id", "course_id", "chat_room_id", "collection_name"
    )
    @classmethod
    def validate_no_path_traversal(cls, v: Optional[str]) -> Optional[str]:
        if v and any(char in v for char in ["..", "/", "\\"]):
            raise ValueError("ID tidak boleh mengandung karakter path traversal")
        return v


class OrchestrationResponse(BaseModel):
    """Response from orchestration with full analytics."""

    success: bool
    bot_response: str
    system_intervention: Optional[str] = None
    intervention_type: Optional[str] = None
    action_taken: str  # FETCH or NO_FETCH
    should_notify_teacher: bool = False
    quality_score: Optional[float] = None
    meta: Dict[str, Any] = {}
    guardrail_outcome: Optional[str] = None
    guardrail_reason: Optional[str] = None
    scaffolding_level: Optional[str] = None
    scaffolding_outcome: Optional[str] = None
    error: Optional[str] = None
    citations: List[Dict[str, Any]] = []


class GroupAnalyticsRequest(BaseModel):
    """Request for group analytics."""

    group_id: str


class GroupAnalyticsResponse(BaseModel):
    """Response with group-level analytics."""

    success: bool
    group_id: str
    message_count: int = 0
    quality_score: Optional[float] = None
    quality_breakdown: Dict[str, float] = {}
    recommendation: Optional[str] = None
    participants: List[str] = []
    participant_count: int = 0
    engagement_distribution: Dict[str, int] = {}
    hot_percentage: Optional[float] = None
    error: Optional[str] = None


class EngagementAnalysisRequest(BaseModel):
    """Request for text engagement analysis."""

    text: str = Field(..., min_length=1, max_length=10000)


class EngagementAnalysisResponse(BaseModel):
    """Response with engagement analysis metrics."""

    success: bool
    lexical_variety: float
    engagement_type: str
    is_higher_order: bool
    hot_indicators: List[str] = []
    word_count: int
    unique_words: int
    confidence: float
    error: Optional[str] = None


class ProcessMiningExportResponse(BaseModel):
    """Response from process mining export."""

    success: bool
    file_url: str
    total_events: int = 0
    unique_cases: int = 0
    message: Optional[str] = None
    error: Optional[str] = None


# ============== Guardrails ==============


class GuardrailCheckRequest(BaseModel):
    """Request for guardrail check."""

    text: str = Field(..., min_length=1, max_length=10000)
    context: Optional[Dict[str, Any]] = None


class GuardrailCheckResponse(BaseModel):
    """Response from guardrail check."""

    allowed: bool
    action: str  # allow, block, warn, redirect, sanitize
    reason: str
    message: Optional[str] = None
    sanitized_text: Optional[str] = None
    triggered_rules: List[str] = []
    confidence: float = 1.0


# ============== Personal AI Chat ==============


class PersonalChatMessage(BaseModel):
    """A message in personal AI chat history."""

    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=10000)


class PersonalChatRequest(BaseModel):
    """Request for personal AI chat (multi-turn, no RAG)."""

    message: str = Field(..., min_length=1, max_length=10000)
    history: List[PersonalChatMessage] = Field(default_factory=list, max_length=50)
    user_name: Optional[str] = None


class PersonalChatResponse(BaseModel):
    """Response from personal AI chat."""

    reply: str
    success: bool = True
    tokens_used: int = 0
    error: Optional[str] = None


class TrackActivityRequest(BaseModel):
    group_id: str
    user_id: Optional[str] = None
