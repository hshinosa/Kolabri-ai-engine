"""
Tests for API Schemas - 100% Coverage
"""

import pytest
from datetime import datetime
from pydantic import ValidationError
from app.api.schemas import (
    HealthResponse,
    PDFUploadResponse,
    DocumentProcessResult,
    BatchUploadResponse,
    IngestResponse,
    DocumentInfo,
    DocumentListResponse,
    QueryRequest,
    ReadingRecommendationRequest,
    AskRequest,
    AskResponse,
    SourceInfo,
    QueryResponse,
    ChatMessage,
    InterventionRequest,
    InterventionResponse,
    SummaryRequest,
    SummaryResponse,
    PromptRequest,
    PromptResponse,
    CreateCollectionRequest,
    CollectionResponse,
    CollectionListResponse,
    ErrorResponse,
    OrchestrationRequest,
    OrchestrationResponse,
    GroupAnalyticsRequest,
    GroupAnalyticsResponse,
    EngagementAnalysisRequest,
    EngagementAnalysisResponse,
    ProcessMiningExportResponse,
    GuardrailCheckRequest,
    GuardrailCheckResponse,
    PersonalChatRequest,
    ProviderContextV1,
)


def build_provider_context() -> ProviderContextV1:
    return ProviderContextV1(
        version="1.0",
        provider={"name": "openai", "displayName": "OpenAI GPT"},
        execution={
            "baseUrl": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
            "temperature": 0.4,
            "maxTokens": 1024,
        },
        auth={"type": "api-key", "credential": "sk-test-credential"},
        metadata={
            "featureFamily": "orchestration",
            "requestId": "req-123",
            "resolvedAt": "2026-06-16T00:00:00.000Z",
        },
    )


class TestProviderContextV1:
    def test_provider_context_valid(self):
        context = build_provider_context()
        assert context.version == "1.0"
        assert context.provider.name == "openai"

    def test_provider_context_invalid_version(self):
        payload = build_provider_context().model_dump()
        payload["version"] = "2.0"
        with pytest.raises(ValidationError):
            ProviderContextV1(**payload)


class TestHealthResponse:
    """Test HealthResponse schema."""

    def test_health_response_valid(self):
        """Test valid health response."""
        response = HealthResponse(
            status="healthy",
            version="1.0.0",
            timestamp=datetime.now(),
            services={"vector_store": True, "llm": True},
        )
        assert response.status == "healthy"
        assert response.version == "1.0.0"
        assert response.services["vector_store"] is True


class TestPDFUploadResponse:
    """Test PDFUploadResponse schema."""

    def test_pdf_upload_response_valid(self):
        """Test valid PDF upload response."""
        response = PDFUploadResponse(
            success=True,
            message="Success",
            document_id="doc_123",
            filename="test.pdf",
            chunks_created=10,
            processing_time_ms=100.5,
        )
        assert response.success is True
        assert response.document_id == "doc_123"
        assert response.chunks_created == 10


class TestDocumentProcessResult:
    """Test DocumentProcessResult schema."""

    def test_document_process_result_valid(self):
        """Test valid document process result."""
        result = DocumentProcessResult(
            filename="test.pdf",
            file_type="pdf",
            chunks_created=5,
            page_count=10,
            image_count=2,
            total_characters=5000,
            processing_time_ms=200.0,
            success=True,
        )
        assert result.filename == "test.pdf"
        assert result.file_type == "pdf"
        assert result.page_count == 10


class TestBatchUploadResponse:
    """Test BatchUploadResponse schema."""

    def test_batch_upload_response_valid(self):
        """Test valid batch upload response."""
        result = BatchUploadResponse(
            success=True,
            message="Processing",
            total_files=3,
            successful_files=3,
            failed_files=0,
            total_chunks=15,
            processing_time_ms=500.0,
        )
        assert result.total_files == 3
        assert result.successful_files == 3


class TestIngestResponse:
    """Test IngestResponse schema."""

    def test_ingest_response_valid(self):
        """Test valid ingest response."""
        response = IngestResponse(
            success=True,
            message="Processing",
            file_id="file_123",
            document_id="doc_123",
            chunks_created=10,
            page_count=5,
            image_count=1,
            file_type="pdf",
            processing_time_ms=300.0,
        )
        assert response.file_id == "file_123"
        assert response.file_type == "pdf"


class TestDocumentInfo:
    """Test DocumentInfo schema."""

    def test_document_info_valid(self):
        """Test valid document info."""
        info = DocumentInfo(
            document_id="doc_123",
            filename="test.pdf",
            course_id="course_1",
            upload_time=datetime.now(),
            chunks_count=10,
            status="processed",
        )
        assert info.document_id == "doc_123"
        assert info.course_id == "course_1"
        assert info.chunks_count == 10


class TestDocumentListResponse:
    """Test DocumentListResponse schema."""

    def test_document_list_response_valid(self):
        """Test valid document list response."""
        info = DocumentInfo(
            document_id="doc_123",
            filename="test.pdf",
            upload_time=datetime.now(),
            chunks_count=10,
            status="processed",
        )
        response = DocumentListResponse(success=True, documents=[info], total=1)
        assert response.success is True
        assert response.total == 1
        assert len(response.documents) == 1


class TestQueryRequest:
    """Test QueryRequest schema."""

    def test_query_request_valid(self):
        """Test valid query request."""
        request = QueryRequest(
            query="What is machine learning?",
            course_id="course_1",
            n_results=5,
            include_sources=True,
        )
        assert request.query == "What is machine learning?"
        assert request.n_results == 5

    def test_query_request_min_length(self):
        """Test query request with minimum length."""
        request = QueryRequest(query="A")
        assert request.query == "A"

    def test_query_request_max_length(self):
        """Test query request with maximum length."""
        request = QueryRequest(query="A" * 2000)
        assert len(request.query) == 2000

    def test_query_request_invalid_n_results(self):
        """Test query request with invalid n_results."""
        with pytest.raises(ValidationError):
            QueryRequest(query="test", n_results=0)

        with pytest.raises(ValidationError):
            QueryRequest(query="test", n_results=21)

    def test_query_request_rejects_path_traversal_in_ids(self):
        with pytest.raises(ValidationError):
            QueryRequest(query="ok", course_id="../evil")
        with pytest.raises(ValidationError):
            QueryRequest(query="ok", chat_room_id="room/sub")


class TestAskRequest:
    """Test AskRequest schema."""

    def test_ask_request_valid(self):
        """Test valid ask request."""
        request = AskRequest(
            query="Explain quantum physics",
            course_id="course_1",
            user_name="John",
            session_discussion_id="chat_1",
        )
        assert request.query == "Explain quantum physics"
        assert request.course_id == "course_1"

    def test_ask_request_rejects_path_traversal(self):
        with pytest.raises(ValidationError):
            AskRequest(query="q", course_id="..\\x", session_discussion_id=None)

    def test_ask_request_accepts_provider_context(self):
        request = AskRequest(
            query="Explain quantum physics",
            course_id="course_1",
            provider_context=build_provider_context(),
        )
        assert request.provider_context is not None
        assert request.provider_context.provider.name == "openai"


class TestReadingRecommendationRequest:
    def test_reading_recommendation_rejects_path_traversal(self):
        with pytest.raises(ValidationError):
            ReadingRecommendationRequest(topic="t", course_id="/bad")

    def test_reading_recommendation_accepts_provider_context(self):
        request = ReadingRecommendationRequest(
            topic="transformer",
            course_id="course_1",
            provider_context=build_provider_context(),
        )
        assert request.provider_context is not None


class TestAskResponse:
    """Test AskResponse schema."""

    def test_ask_response_valid(self):
        """Test valid ask response."""
        response = AskResponse(answer="Quantum physics is...", success=True)
        assert response.answer == "Quantum physics is..."
        assert response.success is True


class TestSourceInfo:
    """Test SourceInfo schema."""

    def test_source_info_valid(self):
        """Test valid source info."""
        source = SourceInfo(
            source="document.pdf", page=5, chunk_index=10, relevance_score=0.85
        )
        assert source.source == "document.pdf"
        assert source.page == 5
        assert source.relevance_score == 0.85


class TestQueryResponse:
    """Test QueryResponse schema."""

    def test_query_response_valid(self):
        """Test valid query response."""
        source = SourceInfo(source="doc.pdf", page=1)
        response = QueryResponse(
            success=True,
            answer="Answer here",
            sources=[source],
            query="What is AI?",
            tokens_used=100,
            processing_time_ms=50.0,
        )
        assert response.success is True
        assert len(response.sources) == 1


class TestChatMessage:
    """Test ChatMessage schema."""

    def test_chat_message_valid(self):
        """Test valid chat message."""
        msg = ChatMessage(
            sender="John",
            content="Hello everyone!",
            timestamp=datetime.now(),
            sender_id="user_123",
        )
        assert msg.sender == "John"
        assert msg.content == "Hello everyone!"


class TestInterventionRequest:
    """Test InterventionRequest schema."""

    def test_intervention_request_valid(self):
        """Test valid intervention request."""
        msg = ChatMessage(sender="John", content="Hello")
        request = InterventionRequest(
            messages=[msg],
            topic="Machine Learning",
            chat_room_id="room_1",
            intervention_type="redirect",
            force=False,
        )
        assert len(request.messages) == 1
        assert request.topic == "Machine Learning"

    def test_intervention_request_accepts_provider_context(self):
        msg = ChatMessage(sender="John", content="Hello")
        request = InterventionRequest(
            messages=[msg],
            topic="Machine Learning",
            chat_room_id="room_1",
            provider_context=build_provider_context(),
        )
        assert request.provider_context is not None


class TestInterventionResponse:
    """Test InterventionResponse schema."""

    def test_intervention_response_valid(self):
        """Test valid intervention response."""
        response = InterventionResponse(
            success=True,
            should_intervene=True,
            message="Please stay on topic",
            intervention_type="redirect",
            confidence=0.85,
            reason="Off-topic detected",
        )
        assert response.should_intervene is True
        assert response.confidence == 0.85


class TestSummaryRequest:
    """Test SummaryRequest schema."""

    def test_summary_request_valid(self):
        """Test valid summary request."""
        msg = ChatMessage(sender="John", content="Discussion")
        request = SummaryRequest(
            messages=[msg], chat_room_id="room_1", include_action_items=True
        )
        assert request.include_action_items is True

    def test_summary_request_accepts_provider_context(self):
        msg = ChatMessage(sender="John", content="Discussion")
        request = SummaryRequest(
            messages=[msg],
            chat_room_id="room_1",
            provider_context=build_provider_context(),
        )
        assert request.provider_context is not None


class TestSummaryResponse:
    """Test SummaryResponse schema."""

    def test_summary_response_valid(self):
        """Test valid summary response."""
        response = SummaryResponse(
            success=True, summary="Discussion about AI", message_count=10
        )
        assert response.summary == "Discussion about AI"
        assert response.message_count == 10


class TestPromptRequest:
    """Test PromptRequest schema."""

    def test_prompt_request_valid(self):
        """Test valid prompt request."""
        request = PromptRequest(
            topic="AI Ethics", context="Discussion about ethics", difficulty="medium"
        )
        assert request.topic == "AI Ethics"
        assert request.difficulty == "medium"

    def test_prompt_request_difficulty_validation(self):
        """Test prompt request difficulty validation."""
        with pytest.raises(ValidationError):
            PromptRequest(topic="AI", difficulty="invalid")

        request_easy = PromptRequest(topic="AI", difficulty="easy")
        assert request_easy.difficulty == "easy"

        request_hard = PromptRequest(topic="AI", difficulty="hard")
        assert request_hard.difficulty == "hard"


class TestPromptResponse:
    """Test PromptResponse schema."""

    def test_prompt_response_valid(self):
        """Test valid prompt response."""
        response = PromptResponse(
            success=True, prompt="What are the ethical implications?", topic="AI Ethics"
        )
        assert response.prompt == "What are the ethical implications?"


class TestCreateCollectionRequest:
    """Test CreateCollectionRequest schema."""

    def test_create_collection_request_valid(self):
        """Test valid create collection request."""
        request = CreateCollectionRequest(
            name="course_materials",
            description="All course materials",
            course_id="course_1",
        )
        assert request.name == "course_materials"
        assert request.course_id == "course_1"


class TestCollectionResponse:
    """Test CollectionResponse schema."""

    def test_collection_response_valid(self):
        """Test valid collection response."""
        response = CollectionResponse(
            success=True,
            name="course_materials",
            document_count=10,
            message="Created successfully",
        )
        assert response.document_count == 10


class TestCollectionListResponse:
    """Test CollectionListResponse schema."""

    def test_collection_list_response_valid(self):
        """Test valid collection list response."""
        response = CollectionListResponse(
            success=True, collections=[{"name": "col1"}, {"name": "col2"}], total=2
        )
        assert response.total == 2
        assert len(response.collections) == 2


class TestErrorResponse:
    """Test ErrorResponse schema."""

    def test_error_response_valid(self):
        """Test valid error response."""
        response = ErrorResponse(
            error="Something went wrong",
            detail="Detailed error message",
            code="ERROR_500",
        )
        assert response.success is False
        assert response.error == "Something went wrong"


class TestOrchestrationRequest:
    """Test OrchestrationRequest schema."""

    def test_orchestration_request_valid(self):
        """Test valid orchestration request."""
        request = OrchestrationRequest(
            user_id="user_123",
            group_id="group_1",
            message="What is machine learning?",
            topic="AI Basics",
            collection_name="course_1",
            course_id="course_1",
        )
        assert request.user_id == "user_123"
        assert request.group_id == "group_1"

    def test_orchestration_request_accepts_provider_context(self):
        request = OrchestrationRequest(
            user_id="user_123",
            group_id="group_1",
            message="What is machine learning?",
            provider_context=build_provider_context(),
        )
        assert request.provider_context is not None

    def test_orchestration_request_rejects_path_traversal(self):
        with pytest.raises(ValidationError):
            OrchestrationRequest(
                user_id="u",
                group_id="g",
                message="hi",
                collection_name="../c",
            )


class TestPersonalChatRequest:
    def test_personal_chat_request_accepts_provider_context(self):
        request = PersonalChatRequest(
            message="Halo",
            history=[],
            provider_context=build_provider_context(),
        )
        assert request.provider_context is not None


class TestOrchestrationResponse:
    """Test OrchestrationResponse schema."""

    def test_orchestration_response_valid(self):
        """Test valid orchestration response."""
        response = OrchestrationResponse(
            success=True,
            bot_response="Machine learning is...",
            system_intervention=None,
            intervention_type=None,
            action_taken="FETCH",
            should_notify_teacher=False,
            quality_score=0.85,
            meta={"lexical_variety": 0.5},
        )
        assert response.action_taken == "FETCH"
        assert response.quality_score == 0.85


class TestGroupAnalyticsRequest:
    """Test GroupAnalyticsRequest schema."""

    def test_group_analytics_request_valid(self):
        """Test valid group analytics request."""
        request = GroupAnalyticsRequest(group_id="group_1")
        assert request.group_id == "group_1"


class TestGroupAnalyticsResponse:
    """Test GroupAnalyticsResponse schema."""

    def test_group_analytics_response_valid(self):
        """Test valid group analytics response."""
        response = GroupAnalyticsResponse(
            success=True,
            group_id="group_1",
            message_count=50,
            quality_score=0.75,
            quality_breakdown={"high": 0.3, "medium": 0.5, "low": 0.2},
            recommendation="Increase participation",
            participants=["user1", "user2"],
            participant_count=2,
            engagement_distribution={"high": 1, "medium": 1, "low": 0},
        )
        assert response.message_count == 50
        assert response.participant_count == 2


class TestEngagementAnalysisRequest:
    """Test EngagementAnalysisRequest schema."""

    def test_engagement_analysis_request_valid(self):
        """Test valid engagement analysis request."""
        request = EngagementAnalysisRequest(text="This is a test message")
        assert len(request.text) > 0

    def test_engagement_analysis_request_max_length(self):
        """Test engagement analysis request with max length."""
        request = EngagementAnalysisRequest(text="A" * 10000)
        assert len(request.text) == 10000


class TestEngagementAnalysisResponse:
    """Test EngagementAnalysisResponse schema."""

    def test_engagement_analysis_response_valid(self):
        """Test valid engagement analysis response."""
        response = EngagementAnalysisResponse(
            success=True,
            lexical_variety=0.65,
            engagement_type="cognitive",
            is_higher_order=True,
            hot_indicators=["explain", "why"],
            word_count=50,
            unique_words=35,
            confidence=0.9,
        )
        assert response.lexical_variety == 0.65
        assert response.is_higher_order is True
        assert len(response.hot_indicators) == 2


class TestProcessMiningExportResponse:
    """Test ProcessMiningExportResponse schema."""

    def test_process_mining_export_response_valid(self):
        """Test valid process mining export response."""
        response = ProcessMiningExportResponse(
            success=True,
            file_url="https://example.com/export.csv",
            total_events=100,
            unique_cases=5,
            message="Export successful",
        )
        assert response.total_events == 100
        assert response.unique_cases == 5


class TestGuardrailCheckRequest:
    """Test GuardrailCheckRequest schema."""

    def test_guardrail_check_request_valid(self):
        """Test valid guardrail check request."""
        request = GuardrailCheckRequest(
            text="Check this text", context={"user_id": "user_123"}
        )
        assert request.text == "Check this text"
        assert request.context["user_id"] == "user_123"


class TestGuardrailCheckResponse:
    """Test GuardrailCheckResponse schema."""

    def test_guardrail_check_response_valid(self):
        """Test valid guardrail check response."""
        response = GuardrailCheckResponse(
            allowed=True,
            action="allow",
            reason="All checks passed",
            message=None,
            sanitized_text=None,
            triggered_rules=[],
            confidence=1.0,
        )
        assert response.allowed is True
        assert response.action == "allow"
        assert response.confidence == 1.0
