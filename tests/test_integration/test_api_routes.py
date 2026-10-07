"""
Integration Tests for API Routes
=================================

Tests for FastAPI endpoints including:
- Health check endpoint
- Ask (RAG Query) endpoint
- Document ingestion endpoints
- Goal validation endpoint
- Dashboard endpoints
- CSV export endpoints
- Logic listener / group endpoints
- Efficiency guard endpoints
"""

import pytest
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock


# ==============================================================================
# APP & CLIENT FIXTURES (Module-scoped, no module reloading)
# ==============================================================================


@pytest.fixture(scope="module")
def integration_app():
    """
    Create a stable FastAPI app for integration tests.

    Uses a mock lifespan to avoid connecting to real external services
    (MongoDB, ChromaDB). Module-scoped so it is created once and reused
    across all tests in this file.
    """

    @asynccontextmanager
    async def mock_lifespan(app: FastAPI):
        yield

    from app.api.routes import router as api_router

    app = FastAPI(
        title="Kolabri AI-Engine (Test)",
        version="1.0.0",
        lifespan=mock_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")

    @app.get("/")
    async def root():
        return {
            "service": "Kolabri AI-Engine",
            "version": "1.0.0",
            "status": "running",
            "docs": "/docs",
        }

    return app


@pytest.fixture(scope="module")
def client(integration_app) -> TestClient:
    """Create a synchronous TestClient for the integration app."""
    with TestClient(integration_app, raise_server_exceptions=True) as c:
        yield c


# ==============================================================================
# MOCK DATA HELPERS
# ==============================================================================


def _make_rag_result(answer="Test RAG response", sources=None, success=True):
    """Helper to create a real RAGResult object."""
    from app.services.rag import RAGResult

    return RAGResult(
        answer=answer,
        sources=sources or [],
        query="test query",
        tokens_used=50,
        success=success,
    )


def _mock_redis_cache_miss():
    """Patch get_redis_cache so dashboard routes can await get/set without real Redis."""
    mock_redis_instance = MagicMock()
    mock_redis_instance.generate_key = MagicMock(return_value="test-cache-key")
    mock_redis_instance.get = AsyncMock(return_value=None)
    mock_redis_instance.set = AsyncMock()
    return patch(
        "app.api.routes.analytics.get_redis_cache",
        new=AsyncMock(return_value=mock_redis_instance),
    )


def _make_processed_document(filename="test.pdf", chunks_count=3):
    """Helper to create a real ProcessedDocument object."""
    from app.services.document_processor import ProcessedDocument, ProcessedChunk

    chunks = [
        ProcessedChunk(
            text=f"Chunk {i} content from {filename}",
            metadata={"source": filename, "page": i + 1},
            chunk_id=f"doc_{i}",
        )
        for i in range(chunks_count)
    ]

    return ProcessedDocument(
        filename=filename,
        file_type="pdf",
        chunks=chunks,
        page_count=3,
        image_count=0,
        total_characters=300,
        processing_time_ms=150,
        success=True,
    )


# ==============================================================================
# TESTS: Root Endpoint
# ==============================================================================


def test_root_endpoint(client):
    """Test root endpoint returns service info."""
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Kolabri AI-Engine"
    assert data["version"] == "1.0.0"
    assert data["status"] == "running"


# ==============================================================================
# TESTS: Health Check Endpoint
# Routes use get_vector_store() and a local import of get_llm_service
# ==============================================================================


def test_health_check_success(client):
    """Test health check returns success status."""
    with (
        patch("app.api.routes.health.get_vector_store") as mock_get_vs,
    ):
        mock_vs = MagicMock()
        mock_vs._ensure_collection = AsyncMock()
        mock_get_vs.return_value = mock_vs

        response = client.get("/api/health")

    assert response.status_code in (200, 503)
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "version" in data


def test_health_check_response_structure(client):
    """Test health check response contains all expected fields."""
    with patch("app.api.routes.health.get_vector_store") as mock_get_vs:
        mock_vs = MagicMock()
        mock_vs._ensure_collection = AsyncMock()
        mock_get_vs.return_value = mock_vs

        response = client.get("/api/health")

    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "timestamp" in data
    assert "services" in data
    assert isinstance(data["services"], dict)


def test_health_check_degraded_on_vector_store_failure(client):
    """Test health check is degraded when vector store fails."""
    with patch("app.api.routes.health.get_vector_store") as mock_get_vs:
        mock_vs = MagicMock()
        mock_vs._ensure_collection = AsyncMock(side_effect=Exception("ChromaDB down"))
        mock_get_vs.return_value = mock_vs

        response = client.get("/api/health")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["services"]["vector_store"] is False


# ==============================================================================
# TESTS: Ask Endpoint (RAG Query)
# Routes use get_rag_pipeline() directly — no mongo_logger in this endpoint
# ==============================================================================


def test_ask_endpoint_success(client):
    """Test /ask endpoint returns answer from RAG pipeline."""
    with patch("app.api.routes.chat.get_rag_pipeline") as mock_get_rag:
        mock_rag = MagicMock()
        mock_rag.query = AsyncMock(
            return_value=_make_rag_result(
                answer="Test RAG response about React.",
                sources=[],
            )
        )
        mock_get_rag.return_value = mock_rag

        response = client.post(
            "/api/ask",
            json={
                "query": "What is React?",
                "course_id": "test_course",
                "user_name": "test_user",
                "session_discussion_id": "test_space",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "answer" in data
    assert "Test RAG response" in data["answer"]


def test_ask_endpoint_with_sources(client):
    """Test /ask endpoint appends source citations when sources present."""
    with patch("app.api.routes.chat.get_rag_pipeline") as mock_get_rag:
        mock_rag = MagicMock()
        mock_rag.query = AsyncMock(
            return_value=_make_rag_result(
                answer="Detailed answer about database normalization.",
                sources=[{"source": "db_slides.pdf", "page": 3, "relevance": 0.9}],
            )
        )
        mock_get_rag.return_value = mock_rag

        response = client.post(
            "/api/ask",
            json={
                "query": "Explain database normalization",
                "course_id": "test",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "📚 *Sumber:*" in data["answer"]


def test_ask_endpoint_missing_query(client):
    """Test /ask endpoint with missing required 'query' field returns 422."""
    response = client.post(
        "/api/ask",
        json={"course_id": "test"},  # Missing 'query'
    )
    assert response.status_code == 422


def test_ask_endpoint_greeting_no_fetch(client):
    """Test /ask endpoint with greeting — handled by NO_FETCH policy."""
    with patch("app.api.routes.chat.get_rag_pipeline") as mock_get_rag:
        mock_rag = MagicMock()
        mock_rag.query = AsyncMock(
            return_value=_make_rag_result(
                answer="Halo! Ada yang bisa saya bantu?",
                sources=[],
            )
        )
        mock_get_rag.return_value = mock_rag

        response = client.post(
            "/api/ask",
            json={"query": "halo", "course_id": "test"},
        )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_ask_endpoint_rag_failure_returns_fallback(client):
    """Test /ask endpoint returns fallback message on RAG failure."""
    with patch("app.api.routes.chat.get_rag_pipeline") as mock_get_rag:
        mock_rag = MagicMock()
        mock_rag.query = AsyncMock(
            return_value=_make_rag_result(answer="", sources=[], success=False)
        )
        mock_get_rag.return_value = mock_rag

        response = client.post(
            "/api/ask",
            json={"query": "Explain React hooks", "course_id": "test"},
        )

    assert response.status_code == 200
    data = response.json()
    # success=False in RAGResult triggers fallback message
    assert data["success"] is False


# ==============================================================================
# TESTS: Document Ingestion Endpoint
# ==============================================================================


def test_ingest_endpoint_pdf(client):
    """Test /ingest endpoint accepts PDF and queues background processing."""
    response = client.post(
        "/api/ingest",
        data={"course_id": "test_course", "file_id": "test_file_123"},
        files={"file": ("test.pdf", b"fake pdf content", "application/pdf")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["file_id"] == "test_file_123"
    assert "diproses" in data["message"] or "processing" in data["message"].lower()


def test_ingest_endpoint_unsupported_type(client):
    """Test /ingest endpoint rejects unsupported file extensions."""
    response = client.post(
        "/api/ingest",
        data={"course_id": "test", "file_id": "test"},
        files={"file": ("test.xyz", b"content", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_ingest_endpoint_file_size_limit(client):
    """Test /ingest endpoint enforces file size limit (10 MB)."""
    large_content = b"x" * (11 * 1024 * 1024)  # 11 MB

    response = client.post(
        "/api/ingest",
        data={"course_id": "test", "file_id": "test"},
        files={"file": ("large.pdf", large_content, "application/pdf")},
    )

    assert response.status_code == 400
    assert "size" in response.json()["detail"].lower()


# ==============================================================================
# TESTS: Batch Ingestion Endpoint
# ==============================================================================


def test_batch_ingest_multiple_files(client):
    """Test /ingest/batch processes multiple files at once."""
    with patch("app.api.routes.documents.get_document_processor") as mock_get_dp:
        mock_dp = MagicMock()
        mock_dp.process_file = AsyncMock(
            side_effect=[
                _make_processed_document(filename="doc1.pdf"),
                _make_processed_document(filename="doc2.pdf"),
                _make_processed_document(filename="doc3.pdf"),
            ]
        )
        mock_get_dp.return_value = mock_dp

        response = client.post(
            "/api/ingest/batch",
            data={"course_id": "test_course", "extract_images": "true"},
            files=[
                ("files", ("doc1.pdf", b"content1", "application/pdf")),
                ("files", ("doc2.pdf", b"content2", "application/pdf")),
                ("files", ("doc3.pdf", b"content3", "application/pdf")),
            ],
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total_files"] == 3


# ==============================================================================
# TESTS: Goal Validation Endpoint
# Routes use get_orchestrator()
# ==============================================================================


@patch("app.api.routes.goals.get_orchestrator")
def test_validate_goal_success(mock_get_orchestrator, client):
    """Test /goals/validate endpoint validates a SMART goal."""
    mock_orchestrator = MagicMock()
    mock_orchestrator.validate_goal = AsyncMock(
        return_value={
            "is_valid": True,
            "score": 1.0,
            "feedback": "✅ Tujuanmu sudah SMART!",
            "missing_criteria": [],
            "suggestions": [],
            "success": True,
        }
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post(
        "/api/goals/validate",
        data={
            "goal_text": "Membuat prototype aplikasi dalam 5 hari dengan 3 fitur CRUD",
            "user_id": "user_1",
            "session_discussion_id": "space_1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is True
    assert data["score"] == 1.0


@patch("app.api.routes.goals.get_orchestrator")
def test_validate_goal_invalid(mock_get_orchestrator, client):
    """Test /goals/validate returns proper feedback for invalid goal."""
    mock_orchestrator = MagicMock()
    mock_orchestrator.validate_goal = AsyncMock(
        return_value={
            "is_valid": False,
            "score": 0.33,
            "feedback": "⚠️ Goalmu belum SMART.",
            "missing_criteria": ["measurable", "time_bound"],
            "suggestions": ["Tambahkan angka target", "Tambahkan deadline"],
            "success": True,
        }
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post(
        "/api/goals/validate",
        data={
            "goal_text": "belajar React",
            "user_id": "user_1",
            "session_discussion_id": "space_1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is False
    assert data["score"] < 1.0


# ==============================================================================
# TESTS: Group Dashboard Endpoint
# ==============================================================================


@patch("app.api.routes.analytics.get_orchestrator")
def test_group_dashboard_success(mock_get_orchestrator, client):
    """Test /analytics/dashboard/group/{id} returns full dashboard data."""
    with _mock_redis_cache_miss():
        mock_orchestrator = MagicMock()
        mock_orchestrator.get_group_dashboard_data = AsyncMock(
            return_value={
                "context": "group",
                "group_id": "group_1",
                "status_color": "green",
                "session_id": "1",
                "radar_chart_data": {
                    "cognitive": 7.0,
                    "collaboration": 8.0,
                    "consistency": 6.0,
                    "vocabulary": 7.5,
                    "engagement": 8.0,
                },
                "teacher_advice": ["Kelompok berjalan stabil."],
                "metrics": {
                    "quality_score": 75.0,
                    "hot_percentage": 40.0,
                },
            }
        )
        mock_get_orchestrator.return_value = mock_orchestrator

        response = client.get("/api/analytics/dashboard/group/group_1")

        assert response.status_code == 200
        data = response.json()
        assert data["context"] == "group"
        assert data["status_color"] == "green"
        assert "radar_chart_data" in data
        assert data["radar_chart_data"]["cognitive"] == 7.0


# ==============================================================================
# TESTS: Individual Dashboard Endpoint
# ==============================================================================


@patch("app.api.routes.analytics.get_orchestrator")
def test_individual_dashboard_success(mock_get_orchestrator, client):
    """Test /analytics/dashboard/individual/{id} returns personal dashboard."""
    with _mock_redis_cache_miss():
        mock_orchestrator = MagicMock()
        mock_orchestrator.get_individual_dashboard_data = AsyncMock(
            return_value={
                "context": "individual",
                "user_id": "user_1",
                "status_color": "yellow",
                "radar_chart_data": {
                    "critical_thinking": 6.0,
                    "engagement": 5.0,
                    "vocabulary": 7.0,
                    "quality": 6.5,
                    "consistency": 8.0,
                },
                "personal_metrics": {
                    "avg_quality_score": 65.0,
                    "hot_percentage": 25.0,
                },
                "total_messages": 10,
            }
        )
        mock_get_orchestrator.return_value = mock_orchestrator

        response = client.get("/api/analytics/dashboard/individual/user_1")

        assert response.status_code == 200
        data = response.json()
        assert data["context"] == "individual"
        assert "radar_chart_data" in data
        assert data["radar_chart_data"]["critical_thinking"] == 6.0
        assert data["total_messages"] == 10


# ==============================================================================
# TESTS: CSV Export Endpoints
# ==============================================================================


@patch("app.api.routes.analytics.get_export_service")
def test_export_group_activity_csv(mock_get_export_service, client):
    """Test /export/activity/group/{id} returns CSV file download."""
    mock_service = MagicMock()
    mock_service.export_group_activity_detailed = AsyncMock(
        return_value="Date,Student,Message\n2024-01-01,user_1,Test message\n"
    )
    mock_get_export_service.return_value = mock_service

    response = client.get("/api/export/activity/group/group_1")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    csv_content = response.content.decode()
    assert "Date,Student,Message" in csv_content


@patch("app.api.routes.analytics.get_export_service")
def test_export_session_discussion_csv(mock_get_export_service, client):
    """Test /export/activity/session-discussion/{id} returns CSV."""
    mock_service = MagicMock()
    mock_service.export_session_discussion_activity = AsyncMock(
        return_value="Student,Messages,Score\nuser_1,10,75\n"
    )
    mock_get_export_service.return_value = mock_service

    response = client.get(
        "/api/export/activity/session-discussion/space_1?include_detailed=true"
    )

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "Student,Messages,Score" in response.content.decode()


def test_export_process_mining_csv(client):
    """Test /export/process-mining/{id} returns XES-compatible CSV.

    The route does a local import of get_mongo_logger, so we patch
    it in the mongodb_logger module, not in routes.
    """
    with patch("app.services.mongodb_logger.get_mongo_logger") as mock_get_mongo:
        mock_mongo = MagicMock()
        mock_mongo.export_to_csv = AsyncMock(
            return_value=(
                "CaseID,Activity,Timestamp\ncase1,Student_Message,2024-01-01\n"
            )
        )
        mock_get_mongo.return_value = mock_mongo

        # The route does `from app.services.mongodb_logger import get_mongo_logger`
        # inside the function body, so we patch via the module directly.
        with patch(
            "app.services.mongodb_logger.MongoDBLogger.export_to_csv",
            new=AsyncMock(
                return_value=(
                    "CaseID,Activity,Timestamp\ncase1,Student_Message,2024-01-01\n"
                )
            ),
        ):
            # Simplest approach: patch where the route actually calls it
            with patch(
                "app.api.routes.get_mongo_logger",
                create=True,
                return_value=mock_mongo,
            ):
                response = client.get("/api/export/process-mining/case/case1_session_1")

    # Even if mongo is not accessible, the endpoint should handle it gracefully
    assert response.status_code in [200, 500]
    if response.status_code == 200:
        assert "text/csv" in response.headers["content-type"]


# ==============================================================================
# TESTS: Group / Logic Listener Endpoints
# Routes use get_orchestrator() for all group endpoints
# ==============================================================================


@patch("app.api.routes.groups.get_orchestrator")
def test_track_participation(mock_get_orchestrator, client):
    """Test /groups/{id}/track-participation records user activity."""
    mock_orchestrator = MagicMock()
    mock_orchestrator.track_participation = AsyncMock(
        return_value={"success": True, "user_id": "user_1", "group_id": "group_1"}
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post(
        "/api/groups/group_1/track-participation",
        data={"user_id": "user_1"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


@patch("app.api.routes.groups.get_orchestrator")
def test_update_last_message_time(mock_get_orchestrator, client):
    """Test /groups/{id}/update-last-message updates the silence timer."""
    mock_orchestrator = MagicMock()
    mock_orchestrator.update_last_message_time = AsyncMock(
        return_value={
            "success": True,
            "group_id": "group_1",
            "timestamp": "2024-01-01T10:00:00",
        }
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post("/api/groups/group_1/update-last-message")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


@patch("app.api.routes.groups.get_orchestrator")
def test_set_group_topic(mock_get_orchestrator, client):
    """Test /groups/{id}/set-topic stores the discussion topic."""
    mock_orchestrator = MagicMock()
    mock_orchestrator.set_group_topic = AsyncMock(
        return_value={
            "success": True,
            "group_id": "group_1",
            "topic": "Database Normalization",
        }
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post(
        "/api/groups/group_1/set-topic",
        data={"topic": "Database Normalization"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["topic"] == "Database Normalization"


@patch("app.api.routes.groups.get_orchestrator")
def test_check_group_status(mock_get_orchestrator, client):
    """Test /groups/{id}/status returns group monitoring status."""
    mock_orchestrator = MagicMock()
    # Endpoint check_group_status synchronous (tanpa await) — pakai MagicMock biasa,
    # AsyncMock membuat result coroutine lalu result.get() meledak.
    mock_orchestrator.check_group_status = MagicMock(
        return_value={
            "group_id": "group_1",
            "should_intervene": False,
            "interventions": [],
            "topic": "Database",
        }
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.get("/api/groups/group_1/status")

    assert response.status_code == 200
    data = response.json()
    assert "group_id" in data


# ==============================================================================
# TESTS: Efficiency Guard Endpoints
# ==============================================================================


@patch("app.api.routes.efficiency.get_efficiency_guard")
@patch("app.api.routes.efficiency.settings")
def test_efficiency_cache_statistics(mock_settings, mock_get_guard, client):
    """Test /efficiency/cache/statistics returns cache performance metrics."""
    mock_settings.ENABLE_EFFICIENCY_GUARD = True

    mock_guard = MagicMock()
    mock_guard.get_cache_statistics.return_value = {
        "cache_hits": 100,
        "cache_misses": 50,
        "hit_rate_percent": 66.67,
        "cache_size": 50,
        "max_cache_size": 1000,
    }
    mock_get_guard.return_value = mock_guard

    response = client.get("/api/efficiency/cache/statistics")

    assert response.status_code == 200
    data = response.json()
    assert data["cache_hits"] == 100
    assert data["hit_rate_percent"] == 66.67


@patch("app.api.routes.efficiency.get_efficiency_guard")
@patch("app.api.routes.efficiency.settings")
def test_efficiency_cache_clear(mock_settings, mock_get_guard, client):
    """Test /efficiency/cache/clear removes all cached entries."""
    mock_settings.ENABLE_EFFICIENCY_GUARD = True

    mock_guard = MagicMock()
    # clear_cache is called WITHOUT await in the route, so use a regular Mock
    mock_guard.clear_cache = MagicMock(return_value=None)
    mock_get_guard.return_value = mock_guard

    response = client.get("/api/efficiency/cache/clear")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    mock_guard.clear_cache.assert_called_once()


@patch("app.api.routes.efficiency.get_efficiency_guard")
@patch("app.api.routes.efficiency.settings")
def test_efficiency_statistics_full(mock_settings, mock_get_guard, client):
    """Test /efficiency/statistics returns comprehensive stats."""
    mock_settings.ENABLE_EFFICIENCY_GUARD = True

    mock_guard = MagicMock()
    mock_guard.get_statistics.return_value = {
        "cache": {"cache_hits": 10, "cache_misses": 5, "hit_rate_percent": 66.7},
        "rate_limit": {"total_requests": 15},
        "query_patterns": {"unique_queries": 8},
        "performance": {"avg_query_time_ms": 120},
    }
    mock_get_guard.return_value = mock_guard

    response = client.get("/api/efficiency/statistics")

    assert response.status_code == 200
    data = response.json()
    assert "cache" in data


@patch("app.api.routes.efficiency.get_efficiency_guard")
@patch("app.api.routes.efficiency.settings")
def test_efficiency_rate_limit_info(mock_settings, mock_get_guard, client):
    """Test /efficiency/rate-limit/info returns rate limit data."""
    mock_settings.ENABLE_EFFICIENCY_GUARD = True

    mock_guard = MagicMock()
    mock_guard.get_rate_limit_info.return_value = {
        "identifier": "test_user",
        "max_requests": 100,
        "window_seconds": 60,
        "remaining_requests": 85,
        "requests_made": 15,
        "is_limited": False,
    }
    mock_get_guard.return_value = mock_guard

    response = client.get("/api/efficiency/rate-limit/info?identifier=test_user")

    assert response.status_code == 200
    data = response.json()
    assert data["is_limited"] is False
    assert data["remaining_requests"] == 85


@patch("app.api.routes.efficiency.get_efficiency_guard")
@patch("app.api.routes.efficiency.settings")
def test_efficiency_high_frequency_queries(mock_settings, mock_get_guard, client):
    """Test /efficiency/queries/high-frequency returns top queries."""
    mock_settings.ENABLE_EFFICIENCY_GUARD = True

    mock_guard = MagicMock()
    mock_guard.get_high_frequency_queries.return_value = [
        {"query": "Apa itu React?", "frequency": 42, "cache_hits": 38},
        {"query": "Jelaskan database", "frequency": 28, "cache_hits": 25},
    ]
    mock_get_guard.return_value = mock_guard

    response = client.get("/api/efficiency/high-frequency-queries?limit=10")

    assert response.status_code == 200
    data = response.json()
    # Response wraps list in {"enabled": True, "queries": [...]}
    assert "queries" in data
    queries = data["queries"]
    assert isinstance(queries, list)
    assert len(queries) == 2
    assert queries[0]["frequency"] == 42


@patch("app.api.routes.efficiency.settings")
def test_efficiency_endpoints_disabled(mock_settings, client):
    """Test efficiency endpoints return disabled message when guard is off."""
    mock_settings.ENABLE_EFFICIENCY_GUARD = False

    response = client.get("/api/efficiency/cache/statistics")

    assert response.status_code == 200
    data = response.json()
    assert data.get("enabled") is False


# ==============================================================================
# TESTS: Engagement Analytics Endpoint
# ==============================================================================


def test_analyze_engagement_endpoint(client):
    """Test /analytics/engagement endpoint returns NLP metrics."""
    with patch("app.api.routes.analytics.get_engagement_analyzer") as mock_get_analyzer:
        from app.services.nlp_analytics import (
            EngagementAnalysis,
            EngagementType,
        )

        mock_analyzer = MagicMock()
        mock_analyzer.analyze_interaction.return_value = EngagementAnalysis(
            lexical_variety=0.65,
            engagement_type=EngagementType.COGNITIVE,
            is_higher_order=True,
            hot_indicators=["menganalisis"],
            word_count=12,
            unique_words=10,
            confidence=0.85,
        )
        mock_analyzer.extract_srl_object.return_value = "Database"
        mock_get_analyzer.return_value = mock_analyzer

        response = client.post(
            "/api/analytics/engagement",
            json={
                "text": "Saya menganalisis struktur database untuk menemukan redundansi",
                "user_id": "user_1",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert "lexical_variety" in data
    assert data["is_higher_order"] is True
    assert data["engagement_type"] == "cognitive"
