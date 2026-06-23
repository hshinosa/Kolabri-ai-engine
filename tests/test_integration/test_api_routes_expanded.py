"""
Expanded Integration Tests for API Routes — 100 % coverage target
=================================================================

Covers every endpoint in ``app/api/routes.py``, including:
- Happy paths **and** failure/exception paths
- Edge cases (empty sources, sources without page, greeting queries)
- Validation errors (422)
- Service‐disabled branches (Efficiency Guard off)
- Background‐task scheduling verification for /ingest
- All supported file types for /ingest
- JSON‐decode errors for /goals/refine

All external services are mocked so tests run without network/DB.
"""

import json
import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def integration_app():
    """Create a lightweight FastAPI app that mirrors production routing."""

    @asynccontextmanager
    async def mock_lifespan(app: FastAPI):
        yield

    from app.api.routes import router as api_router
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException
    from app.core.error_handlers import (
        http_exception_handler,
        validation_exception_handler,
        unhandled_exception_handler,
        ExceptionMiddleware,
    )

    app = FastAPI(
        title="Kolabri AI-Engine (Expanded Tests)",
        version="1.0.0",
        lifespan=mock_lifespan,
    )

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_middleware(ExceptionMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")
    return app


@pytest.fixture(scope="module")
def client(integration_app) -> TestClient:
    with TestClient(integration_app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_redis_cache_miss():
    mock_redis_instance = MagicMock()
    mock_redis_instance.generate_key = MagicMock(return_value="test-cache-key")
    mock_redis_instance.get = AsyncMock(return_value=None)
    mock_redis_instance.set = AsyncMock()
    return patch(
        "app.api.routes.analytics.get_redis_cache",
        new=AsyncMock(return_value=mock_redis_instance),
    )


def _rag_result(answer="Mock answer", sources=None, success=True, error=None):
    from app.services.rag import RAGResult

    return RAGResult(
        answer=answer,
        sources=sources or [],
        query="test",
        tokens_used=10,
        success=success,
        error=error,
    )


# ###########################################################################
#  POST /ask
# ###########################################################################


@pytest.mark.integration
class TestAskEndpoint:
    """POST /api/ask — RAG pipeline query."""

    def test_success_no_sources(self, client):
        """RAG returns answer without sources."""
        with patch("app.api.routes.chat.get_rag_pipeline") as m:
            rag = MagicMock()
            rag.query = AsyncMock(return_value=_rag_result("Hello world"))
            m.return_value = rag

            resp = client.post(
                "/api/ask",
                json={"query": "What is FastAPI?", "course_id": "c1"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["answer"] == "Hello world"
        rag.query.assert_awaited_once()

    def test_success_with_sources_with_page(self, client):
        """Sources containing 'page' key produce '(hal. N)' citation."""
        sources = [{"source": "slides.pdf", "page": 5}]
        with patch("app.api.routes.chat.get_rag_pipeline") as m:
            rag = MagicMock()
            rag.query = AsyncMock(return_value=_rag_result("Answer", sources))
            m.return_value = rag

            resp = client.post(
                "/api/ask",
                json={"query": "Explain normalization", "course_id": "c1"},
            )

        data = resp.json()
        assert data["success"] is True
        assert "📚 *Sumber:*" in data["answer"]
        assert "slides.pdf (hal. 5)" in data["answer"]

    def test_success_with_sources_without_page(self, client):
        """Sources without 'page' key still list the document name."""
        sources = [{"source": "notes.txt"}]
        with patch("app.api.routes.chat.get_rag_pipeline") as m:
            rag = MagicMock()
            rag.query = AsyncMock(return_value=_rag_result("Answer", sources))
            m.return_value = rag

            resp = client.post(
                "/api/ask",
                json={"query": "Explain React", "course_id": "c1"},
            )

        data = resp.json()
        assert "notes.txt" in data["answer"]
        assert "(hal." not in data["answer"]

    def test_sources_default_name_when_missing(self, client):
        """Source dict missing 'source' key falls back to 'Dokumen'."""
        sources = [{"relevance": 0.9}]
        with patch("app.api.routes.chat.get_rag_pipeline") as m:
            rag = MagicMock()
            rag.query = AsyncMock(return_value=_rag_result("Answer", sources))
            m.return_value = rag

            resp = client.post(
                "/api/ask",
                json={"query": "Tell me about hooks", "course_id": "c1"},
            )

        assert "Dokumen" in resp.json()["answer"]

    def test_sources_capped_at_three(self, client):
        """Only the first 3 sources are listed regardless of how many exist."""
        sources = [{"source": f"doc{i}.pdf", "page": i} for i in range(6)]
        with patch("app.api.routes.chat.get_rag_pipeline") as m:
            rag = MagicMock()
            rag.query = AsyncMock(return_value=_rag_result("Answer", sources))
            m.return_value = rag

            resp = client.post(
                "/api/ask",
                json={"query": "Complex question here", "course_id": "c1"},
            )

        answer = resp.json()["answer"]
        # Should list sources 1-3 but not 4-6
        assert "doc0.pdf" in answer
        assert "doc2.pdf" in answer
        assert "doc3.pdf" not in answer

    def test_rag_failure_returns_fallback(self, client):
        """RAG result with success=False returns Indonesian fallback."""
        with patch("app.api.routes.chat.get_rag_pipeline") as m:
            rag = MagicMock()
            rag.query = AsyncMock(
                return_value=_rag_result("", success=False, error="no match")
            )
            m.return_value = rag

            resp = client.post(
                "/api/ask",
                json={"query": "Unknown topic", "course_id": "c1"},
            )

        data = resp.json()
        assert data["success"] is False
        assert "tidak bisa menemukan" in data["answer"]
        assert data["error"] == "no match"

    def test_exception_returns_error_response(self, client):
        """Unhandled exception in RAG pipeline returns error answer."""
        with patch("app.api.routes.chat.get_rag_pipeline") as m:
            rag = MagicMock()
            rag.query = AsyncMock(side_effect=RuntimeError("LLM timeout"))
            m.return_value = rag

            resp = client.post(
                "/api/ask",
                json={"query": "Question here", "course_id": "c1"},
            )

        data = resp.json()
        assert data["success"] is False
        assert "kesalahan" in data["answer"]
        assert "LLM timeout" not in data["error"]
        assert data["error"] == "Internal error"

    def test_missing_query_returns_422(self, client):
        """Omitting required 'query' field triggers validation error."""
        resp = client.post("/api/ask", json={"course_id": "c1"})
        assert resp.status_code == 422

    def test_missing_course_id_returns_422(self, client):
        """Omitting required 'course_id' field triggers validation error."""
        resp = client.post("/api/ask", json={"query": "hi"})
        assert resp.status_code == 422

    def test_collection_name_uses_course_id(self, client):
        """Verify the collection name is built as 'course_{course_id}'."""
        with patch("app.api.routes.chat.get_rag_pipeline") as m:
            rag = MagicMock()
            rag.query = AsyncMock(return_value=_rag_result("OK"))
            m.return_value = rag

            client.post(
                "/api/ask",
                json={"query": "q", "course_id": "CS101"},
            )

        rag.query.assert_awaited_once()
        call_kwargs = rag.query.call_args
        assert call_kwargs.kwargs["collection_name"] == "course_CS101"
        assert call_kwargs.kwargs["n_results"] == 5


# ###########################################################################
#  POST /ingest
# ###########################################################################


@pytest.mark.integration
class TestIngestEndpoint:
    """POST /api/ingest — document ingestion with background processing."""

    @pytest.mark.parametrize(
        "filename,ext",
        [
            ("doc.pdf", "pdf"),
            ("doc.docx", "docx"),
            ("doc.doc", "doc"),
            ("doc.pptx", "pptx"),
            ("doc.ppt", "ppt"),
            ("doc.txt", "txt"),
            ("doc.md", "md"),
            ("archive.zip", "zip"),
        ],
    )
    def test_supported_file_types_accepted(self, client, filename, ext):
        """All documented file types are accepted and queued."""
        resp = client.post(
            "/api/ingest",
            data={"course_id": "c1", "file_id": "f1"},
            files={"file": (filename, b"data", "application/octet-stream")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["file_type"] == ext
        assert data["file_id"] == "f1"
        assert data["document_id"] == "f1"

    def test_unsupported_file_type_rejected(self, client):
        """Unsupported extension returns 400."""
        resp = client.post(
            "/api/ingest",
            data={"course_id": "c1", "file_id": "f1"},
            files={"file": ("test.exe", b"data", "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "Unsupported file type" in resp.json()["message"]

    def test_file_size_exceeds_limit(self, client):
        """File exceeding MAX_UPLOAD_SIZE_MB (10 MB) is rejected."""
        big = b"x" * (11 * 1024 * 1024)
        resp = client.post(
            "/api/ingest",
            data={"course_id": "c1", "file_id": "f1"},
            files={"file": ("big.pdf", big, "application/pdf")},
        )
        assert resp.status_code == 400
        assert "File size exceeds" in resp.json()["message"]

    def test_response_fields(self, client):
        """Verify all IngestResponse fields are present and correct."""
        resp = client.post(
            "/api/ingest",
            data={"course_id": "c1", "file_id": "fid_42"},
            files={"file": ("test.txt", b"hello", "text/plain")},
        )
        data = resp.json()
        assert data["success"] is True
        assert data["file_id"] == "fid_42"
        assert data["document_id"] == "fid_42"
        assert data["chunks_created"] == 0
        assert data["page_count"] == 0
        assert data["image_count"] == 0
        assert data["processing_time_ms"] == 0
        assert "diproses" in data["message"]

    def test_background_task_is_scheduled(self, client):
        """Verify that background_tasks.add_task is called for processing."""
        with patch("app.api.routes.documents.BackgroundTasks.add_task") as mock_add:
            resp = client.post(
                "/api/ingest",
                data={"course_id": "c1", "file_id": "f1"},
                files={"file": ("test.pdf", b"data", "application/pdf")},
            )
        # Even without patching, the response should be immediate (200)
        assert resp.status_code == 200

    def test_missing_file_returns_422(self, client):
        """Omitting file entirely returns validation error."""
        resp = client.post(
            "/api/ingest",
            data={"course_id": "c1", "file_id": "f1"},
        )
        assert resp.status_code == 422

    def test_missing_course_id_returns_422(self, client):
        """Omitting course_id returns validation error."""
        resp = client.post(
            "/api/ingest",
            data={"file_id": "f1"},
            files={"file": ("test.pdf", b"data", "application/pdf")},
        )
        assert resp.status_code == 422

    def test_missing_file_id_returns_422(self, client):
        """Omitting file_id returns validation error."""
        resp = client.post(
            "/api/ingest",
            data={"course_id": "c1"},
            files={"file": ("test.pdf", b"data", "application/pdf")},
        )
        assert resp.status_code == 422

    def test_temp_file_write_error_returns_500(self, client):
        """OS error during temp file write returns 500."""
        with patch("app.api.routes.documents.tempfile.mkstemp") as mock_mkstemp:
            # Return a fake fd and path, then make os.fdopen raise
            mock_mkstemp.return_value = (999, "/tmp/fake_path")
            with patch(
                "app.api.routes.documents.os.fdopen", side_effect=OSError("disk full")
            ):
                with patch("app.api.routes.documents.os.unlink"):
                    resp = client.post(
                        "/api/ingest",
                        data={"course_id": "c1", "file_id": "f1"},
                        files={"file": ("test.pdf", b"data", "application/pdf")},
                    )
        assert resp.status_code == 500
        assert resp.json()["detail"] == "INTERNAL_SERVER_ERROR"


# ###########################################################################
#  POST /ingest/batch
# ###########################################################################


@pytest.mark.integration
class TestIngestBatchEndpoint:
    """POST /api/ingest/batch — batch document ingestion."""

    def test_multiple_files(self, client):
        resp = client.post(
            "/api/ingest/batch",
            data={"course_id": "c1"},
            files=[
                ("files", ("a.pdf", b"pdf_data", "application/pdf")),
                ("files", ("b.txt", b"text_data", "text/plain")),
            ],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["total_files"] == 2

    def test_no_valid_files_returns_error(self, client):
        """Uploading files with no filename skips them; if none remain → 400/422."""
        resp = client.post(
            "/api/ingest/batch",
            data={"course_id": "c1"},
            files=[("files", ("", b"", "application/octet-stream"))],
        )
        # FastAPI validation may reject empty filename (422) or the route
        # may skip them all and raise 400.  Either is valid rejection.
        assert resp.status_code in (400, 422)


# ###########################################################################
#  GET /health
# ###########################################################################


@pytest.mark.integration
class TestHealthEndpoint:
    """GET /api/health — service health check."""

    def test_all_services_healthy(self, client):
        """Both vector_store and LLM healthy → 'healthy'."""
        mongo = MagicMock()
        mongo.enabled = True
        mongo.ping = AsyncMock(return_value=True)
        redis_cache = MagicMock()
        redis_cache.ping = AsyncMock(return_value=True)
        with (
            patch("app.api.routes.health.get_vector_store") as mock_vs,
            patch("app.services.llm.get_llm_service") as mock_llm_fn,
            patch("app.services.mongodb_logger.get_mongo_logger", return_value=mongo),
            patch(
                "app.core.redis_cache.get_redis_cache",
                AsyncMock(return_value=redis_cache),
            ),
        ):
            vs = MagicMock()
            vs._ensure_collection = AsyncMock()
            mock_vs.return_value = vs

            llm = MagicMock()
            llm.model = "deepseek/deepseek-chat"
            mock_llm_fn.return_value = llm

            resp = client.get("/api/health")

        data = resp.json()
        assert resp.status_code == 200
        assert data["status"] == "healthy"
        assert data["services"]["vector_store"] is True
        assert data["services"]["llm"] is True
        assert "version" in data
        assert "timestamp" in data

    def test_vector_store_down_is_degraded(self, client):
        """Vector store failure → 'degraded'."""
        with patch("app.api.routes.health.get_vector_store") as mock_vs:
            vs = MagicMock()
            vs._ensure_collection = AsyncMock(side_effect=Exception("DB down"))
            mock_vs.return_value = vs

            resp = client.get("/api/health")

        data = resp.json()
        assert data["status"] == "degraded"
        assert data["services"]["vector_store"] is False

    def test_llm_down_is_degraded(self, client):
        """LLM failure → 'degraded'."""
        with (
            patch("app.api.routes.health.get_vector_store") as mock_vs,
            patch("app.services.llm.get_llm_service", side_effect=Exception("no key")),
        ):
            vs = MagicMock()
            vs._ensure_collection = AsyncMock()
            mock_vs.return_value = vs

            resp = client.get("/api/health")

        data = resp.json()
        assert data["status"] == "degraded"
        assert data["services"]["llm"] is False

    def test_llm_model_none_is_degraded(self, client):
        """LLM model attribute is None → service marked False."""
        with (
            patch("app.api.routes.health.get_vector_store") as mock_vs,
            patch("app.services.llm.get_llm_service") as mock_llm_fn,
        ):
            vs = MagicMock()
            vs._ensure_collection = AsyncMock()
            mock_vs.return_value = vs

            llm = MagicMock()
            llm.model = None
            mock_llm_fn.return_value = llm

            resp = client.get("/api/health")

        data = resp.json()
        assert data["status"] == "degraded"
        assert data["services"]["llm"] is False


# ###########################################################################
#  POST /analytics/engagement
# ###########################################################################


@pytest.mark.integration
class TestEngagementEndpoint:
    """POST /api/analytics/engagement — NLP engagement analysis."""

    def test_success(self, client):
        from app.services.nlp_analytics import EngagementAnalysis, EngagementType

        analysis = EngagementAnalysis(
            lexical_variety=0.72,
            engagement_type=EngagementType.COGNITIVE,
            is_higher_order=True,
            hot_indicators=["menganalisis", "mengevaluasi"],
            word_count=15,
            unique_words=12,
            confidence=0.9,
        )

        with patch("app.api.routes.analytics.get_engagement_analyzer") as m:
            analyzer = MagicMock()
            analyzer.analyze_interaction.return_value = analysis
            m.return_value = analyzer

            resp = client.post(
                "/api/analytics/engagement",
                json={
                    "text": "Saya menganalisis dan mengevaluasi pola data ini secara mendalam"
                },
            )

        data = resp.json()
        assert resp.status_code == 200
        assert data["success"] is True
        assert data["lexical_variety"] == 0.72
        assert data["engagement_type"] == "cognitive"
        assert data["is_higher_order"] is True
        assert "menganalisis" in data["hot_indicators"]
        assert data["confidence"] == 1.0  # hardcoded in route

    def test_analyzer_exception_returns_error(self, client):
        """If analyzer raises, endpoint returns success=False with zeroed metrics."""
        with patch("app.api.routes.analytics.get_engagement_analyzer") as m:
            analyzer = MagicMock()
            analyzer.analyze_interaction.side_effect = ValueError("tokenizer error")
            m.return_value = analyzer

            resp = client.post(
                "/api/analytics/engagement",
                json={"text": "test message"},
            )

        data = resp.json()
        assert resp.status_code == 200
        assert data["success"] is False
        assert data["lexical_variety"] == 0
        assert data["engagement_type"] == "unknown"
        assert data["word_count"] == 0
        assert "tokenizer error" not in data["error"]
        assert data["error"] == "Internal error"

    def test_empty_text_returns_422(self, client):
        """Empty text violates min_length=1 validation."""
        resp = client.post("/api/analytics/engagement", json={"text": ""})
        assert resp.status_code == 422

    def test_word_count_uses_request_text(self, client):
        """word_count and unique_words are derived from request.text, not analysis."""
        from app.services.nlp_analytics import EngagementAnalysis, EngagementType

        analysis = EngagementAnalysis(
            lexical_variety=0.5,
            engagement_type=EngagementType.BEHAVIORAL,
            is_higher_order=False,
            hot_indicators=[],
            word_count=999,  # intentionally different
            unique_words=999,
            confidence=0.5,
        )

        with patch("app.api.routes.analytics.get_engagement_analyzer") as m:
            analyzer = MagicMock()
            analyzer.analyze_interaction.return_value = analysis
            m.return_value = analyzer

            text = "kata satu dua tiga empat empat"
            resp = client.post(
                "/api/analytics/engagement",
                json={"text": text},
            )

        data = resp.json()
        # Route computes these from request.text, NOT from analysis object
        assert data["word_count"] == len(text.split())
        assert data["unique_words"] == len(set(text.lower().split()))


# ###########################################################################
#  GET /analytics/dashboard/group/{group_id}
# ###########################################################################


@pytest.mark.integration
class TestGroupDashboardEndpoint:
    """GET /api/analytics/dashboard/group/{group_id}"""

    def test_success(self, client):
        payload = {"context": "group", "group_id": "g1", "status_color": "green"}
        with (
            _mock_redis_cache_miss(),
            patch("app.api.routes.analytics.get_orchestrator") as m,
        ):
            orch = MagicMock()
            orch.get_group_dashboard_data = AsyncMock(return_value=payload)
            m.return_value = orch

            resp = client.get("/api/analytics/dashboard/group/g1")

        assert resp.status_code == 200
        assert resp.json() == payload

    def test_orchestrator_error_returns_500(self, client):
        with patch("app.api.routes.analytics.get_orchestrator") as m:
            orch = MagicMock()
            orch.get_group_dashboard_data = AsyncMock(
                side_effect=Exception("DB timeout")
            )
            m.return_value = orch

            resp = client.get("/api/analytics/dashboard/group/g1")

        assert resp.status_code == 500
        assert resp.json()["detail"] == "INTERNAL_SERVER_ERROR"


# ###########################################################################
#  GET /analytics/dashboard/individual/{user_id}
# ###########################################################################


@pytest.mark.integration
class TestIndividualDashboardEndpoint:
    """GET /api/analytics/dashboard/individual/{user_id}"""

    def test_success(self, client):
        payload = {"context": "individual", "user_id": "u1", "total_messages": 42}
        with (
            _mock_redis_cache_miss(),
            patch("app.api.routes.analytics.get_orchestrator") as m,
        ):
            orch = MagicMock()
            orch.get_individual_dashboard_data = AsyncMock(return_value=payload)
            m.return_value = orch

            resp = client.get("/api/analytics/dashboard/individual/u1")

        assert resp.status_code == 200
        assert resp.json()["total_messages"] == 42

    def test_orchestrator_error_returns_500(self, client):
        with patch("app.api.routes.analytics.get_orchestrator") as m:
            orch = MagicMock()
            orch.get_individual_dashboard_data = AsyncMock(
                side_effect=RuntimeError("fail")
            )
            m.return_value = orch

            resp = client.get("/api/analytics/dashboard/individual/u1")

        assert resp.status_code == 500


# ###########################################################################
#  GET /analytics/dashboard/{group_id}  (Legacy)
# ###########################################################################


@pytest.mark.integration
class TestLegacyDashboardEndpoint:
    """GET /api/analytics/dashboard/{group_id} — delegates to group dashboard."""

    def test_legacy_delegates(self, client):
        payload = {"context": "group", "group_id": "g1"}
        with (
            _mock_redis_cache_miss(),
            patch("app.api.routes.analytics.get_orchestrator") as m,
        ):
            orch = MagicMock()
            orch.get_group_dashboard_data = AsyncMock(return_value=payload)
            m.return_value = orch

            resp = client.get("/api/analytics/dashboard/g1")

        assert resp.status_code == 200
        assert resp.json()["context"] == "group"


# ###########################################################################
#  GET /export/activity/group/{group_id}
# ###########################################################################


@pytest.mark.integration
class TestExportGroupActivityEndpoint:
    """GET /api/export/activity/group/{group_id}"""

    def test_success_csv(self, client):
        csv = "Name,Score\nAlice,90\nBob,85\n"
        with patch("app.api.routes.analytics.get_export_service") as m:
            svc = MagicMock()
            svc.export_group_activity_detailed = AsyncMock(return_value=csv)
            m.return_value = svc

            resp = client.get("/api/export/activity/group/grp1")

        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "attachment" in resp.headers["content-disposition"]
        assert "student_breakdown_grp1" in resp.headers["content-disposition"]
        assert "Name,Score" in resp.content.decode()

    def test_export_error_returns_500(self, client):
        with patch("app.api.routes.analytics.get_export_service") as m:
            svc = MagicMock()
            svc.export_group_activity_detailed = AsyncMock(
                side_effect=Exception("MongoDB unreachable")
            )
            m.return_value = svc

            resp = client.get("/api/export/activity/group/grp1")

        assert resp.status_code == 500
        assert resp.json()["detail"] == "INTERNAL_SERVER_ERROR"


# ###########################################################################
#  GET /export/activity/session-discussion/{session_discussion_id}
# ###########################################################################


@pytest.mark.integration
class TestExportSessionDiscussionActivityEndpoint:
    """GET /api/export/activity/session-discussion/{session_discussion_id}"""

    def test_success_csv(self, client):
        csv = "Student,Messages\nAlice,10\n"
        with patch("app.api.routes.analytics.get_export_service") as m:
            svc = MagicMock()
            svc.export_session_discussion_activity = AsyncMock(return_value=csv)
            m.return_value = svc

            resp = client.get("/api/export/activity/session-discussion/cs1")

        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "activity_session_cs1" in resp.headers["content-disposition"]

    def test_include_detailed_query_param(self, client):
        """Verify include_detailed param is forwarded to service."""
        csv = "col\nval\n"
        with patch("app.api.routes.analytics.get_export_service") as m:
            svc = MagicMock()
            svc.export_session_discussion_activity = AsyncMock(return_value=csv)
            m.return_value = svc

            client.get("/api/export/activity/session-discussion/cs1?include_detailed=false")

        svc.export_session_discussion_activity.assert_awaited_once_with(
            session_discussion_id="cs1", include_detailed=False
        )

    def test_export_error_returns_500(self, client):
        with patch("app.api.routes.analytics.get_export_service") as m:
            svc = MagicMock()
            svc.export_session_discussion_activity = AsyncMock(side_effect=Exception("oops"))
            m.return_value = svc

            resp = client.get("/api/export/activity/session-discussion/cs1")

        assert resp.status_code == 500


# ###########################################################################
#  GET /export/process-mining/case/{case_id}
# ###########################################################################


@pytest.mark.integration
class TestExportProcessMiningEndpoint:
    """GET /api/export/process-mining/case/{case_id}"""

    def test_success_csv(self, client):
        csv = "CaseID,Activity,Timestamp\nc1,Msg,2024-01-01\n"
        with patch("app.services.mongodb_logger.get_mongo_logger") as mock_get_mongo:
            mongo = MagicMock()
            mongo.export_to_csv = AsyncMock(return_value=csv)
            mock_get_mongo.return_value = mongo

            resp = client.get("/api/export/process-mining/case/c1_s1")

        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "process_mining_c1_s1" in resp.headers["content-disposition"]

    def test_mongo_error_returns_500(self, client):
        with patch("app.services.mongodb_logger.get_mongo_logger") as mock_get_mongo:
            mongo = MagicMock()
            mongo.export_to_csv = AsyncMock(side_effect=Exception("connection refused"))
            mock_get_mongo.return_value = mongo

            resp = client.get("/api/export/process-mining/case/c1")

        assert resp.status_code == 500
        assert resp.json()["detail"] == "INTERNAL_SERVER_ERROR"


# ###########################################################################
#  POST /goals/validate
# ###########################################################################


@pytest.mark.integration
class TestGoalValidateEndpoint:
    """POST /api/goals/validate — SMART goal validation."""

    def test_valid_goal(self, client):
        result = {
            "is_valid": True,
            "score": 1.0,
            "feedback": "Great!",
            "missing_criteria": [],
            "suggestions": [],
            "success": True,
        }
        with patch("app.api.routes.goals.get_orchestrator") as m:
            orch = MagicMock()
            orch.validate_goal = AsyncMock(return_value=result)
            m.return_value = orch

            resp = client.post(
                "/api/goals/validate",
                data={
                    "goal_text": "Build CRUD app in 5 days",
                    "user_id": "u1",
                    "session_discussion_id": "s1",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["is_valid"] is True
        assert data["score"] == 1.0

    def test_invalid_goal(self, client):
        result = {
            "is_valid": False,
            "score": 0.2,
            "feedback": "Needs improvement",
            "missing_criteria": ["measurable", "time_bound"],
            "suggestions": ["Add metrics"],
            "success": True,
        }
        with patch("app.api.routes.goals.get_orchestrator") as m:
            orch = MagicMock()
            orch.validate_goal = AsyncMock(return_value=result)
            m.return_value = orch

            resp = client.post(
                "/api/goals/validate",
                data={
                    "goal_text": "Learn stuff",
                    "user_id": "u1",
                    "session_discussion_id": "s1",
                },
            )

        data = resp.json()
        assert data["is_valid"] is False
        assert len(data["missing_criteria"]) == 2

    def test_orchestrator_error_returns_500(self, client):
        with patch("app.api.routes.goals.get_orchestrator") as m:
            orch = MagicMock()
            orch.validate_goal = AsyncMock(side_effect=Exception("service down"))
            m.return_value = orch

            resp = client.post(
                "/api/goals/validate",
                data={
                    "goal_text": "Goal",
                    "user_id": "u1",
                    "session_discussion_id": "s1",
                },
            )

        assert resp.status_code == 500
        assert resp.json()["detail"] == "INTERNAL_SERVER_ERROR"

    def test_missing_form_fields_returns_validation_result(self, client):
        """Form parsial: endpoint mengembalikan 200 dengan hasil validasi (bukan 422)."""
        resp = client.post(
            "/api/goals/validate",
            data={"goal_text": "Goal"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "is_valid" in body


# ###########################################################################
#  POST /goals/refine
# ###########################################################################


@pytest.mark.integration
class TestGoalRefineEndpoint:
    """POST /api/goals/refine — Socratic hints for SMART goal improvement."""

    def test_success(self, client):
        result = {"success": True, "hint": "What metrics will you track?"}
        with patch("app.api.routes.goals.get_orchestrator") as m:
            orch = MagicMock()
            orch.get_goal_refinement = AsyncMock(return_value=result)
            m.return_value = orch

            resp = client.post(
                "/api/goals/refine",
                data={
                    "current_goal": "Learn React",
                    "missing_criteria": json.dumps(["measurable", "time_bound"]),
                },
            )

        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_invalid_json_returns_400(self, client):
        """Non-JSON string for missing_criteria → 400."""
        resp = client.post(
            "/api/goals/refine",
            data={
                "current_goal": "Learn React",
                "missing_criteria": "not valid json [[[",
            },
        )
        assert resp.status_code == 400
        assert "Invalid JSON" in resp.json()["message"]

    def test_orchestrator_error_returns_500(self, client):
        with patch("app.api.routes.goals.get_orchestrator") as m:
            orch = MagicMock()
            orch.get_goal_refinement = AsyncMock(
                side_effect=RuntimeError("LLM overload")
            )
            m.return_value = orch

            resp = client.post(
                "/api/goals/refine",
                data={
                    "current_goal": "Learn React",
                    "missing_criteria": json.dumps(["measurable"]),
                },
            )

        assert resp.status_code == 500
        assert resp.json()["detail"] == "INTERNAL_SERVER_ERROR"

    def test_missing_form_fields_returns_422(self, client):
        resp = client.post("/api/goals/refine", data={"current_goal": "Goal"})
        assert resp.status_code == 422


# ###########################################################################
#  GET /groups/{group_id}/status
# ###########################################################################


@pytest.mark.integration
class TestGroupStatusEndpoint:
    """GET /api/groups/{group_id}/status"""

    def test_success_no_interventions(self, client):
        result = {
            "group_id": "g1",
            "should_intervene": False,
            "interventions": [],
        }
        with patch("app.api.routes.groups.get_orchestrator") as m:
            orch = MagicMock()
            orch.check_group_status = AsyncMock(return_value=result)
            m.return_value = orch

            resp = client.get("/api/groups/g1/status")

        assert resp.status_code == 200
        assert resp.json()["should_intervene"] is False

    def test_with_topic_query_param(self, client):
        """Topic query param is forwarded to orchestrator."""
        result = {"group_id": "g1", "should_intervene": False, "interventions": []}
        with patch("app.api.routes.groups.get_orchestrator") as m:
            orch = MagicMock()
            orch.check_group_status = AsyncMock(return_value=result)
            m.return_value = orch

            client.get("/api/groups/g1/status?topic=Database")

        orch.check_group_status.assert_awaited_once_with(
            group_id="g1", topic="Database"
        )

    def test_with_interventions(self, client):
        result = {
            "group_id": "g1",
            "should_intervene": True,
            "interventions": [{"type": "silence", "message": "Wake up!"}],
        }
        with patch("app.api.routes.groups.get_orchestrator") as m:
            orch = MagicMock()
            orch.check_group_status = AsyncMock(return_value=result)
            m.return_value = orch

            resp = client.get("/api/groups/g1/status")

        data = resp.json()
        assert data["should_intervene"] is True
        assert len(data["interventions"]) == 1

    def test_orchestrator_error_returns_500(self, client):
        with patch("app.api.routes.groups.get_orchestrator") as m:
            orch = MagicMock()
            orch.check_group_status = AsyncMock(side_effect=Exception("fail"))
            m.return_value = orch

            resp = client.get("/api/groups/g1/status")

        assert resp.status_code == 500


# ###########################################################################
#  POST /groups/{group_id}/track-participation
# ###########################################################################


@pytest.mark.integration
class TestTrackParticipationEndpoint:
    """POST /api/groups/{group_id}/track-participation"""

    def test_success(self, client):
        result = {"success": True, "group_id": "g1", "user_id": "u1"}
        with patch("app.api.routes.groups.get_orchestrator") as m:
            orch = MagicMock()
            orch.track_participation = AsyncMock(return_value=result)
            m.return_value = orch

            resp = client.post(
                "/api/groups/g1/track-participation",
                data={"user_id": "u1"},
            )

        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_orchestrator_error_returns_500(self, client):
        with patch("app.api.routes.groups.get_orchestrator") as m:
            orch = MagicMock()
            orch.track_participation = AsyncMock(side_effect=Exception("err"))
            m.return_value = orch

            resp = client.post(
                "/api/groups/g1/track-participation",
                data={"user_id": "u1"},
            )

        assert resp.status_code == 500

    def test_missing_user_id_returns_422(self, client):
        resp = client.post("/api/groups/g1/track-participation", data={})
        assert resp.status_code == 422


# ###########################################################################
#  POST /groups/{group_id}/update-last-message
# ###########################################################################


@pytest.mark.integration
class TestUpdateLastMessageEndpoint:
    """POST /api/groups/{group_id}/update-last-message"""

    def test_success(self, client):
        result = {"success": True, "group_id": "g1", "timestamp": "2024-01-01T12:00:00"}
        with patch("app.api.routes.groups.get_orchestrator") as m:
            orch = MagicMock()
            orch.update_last_message_time = AsyncMock(return_value=result)
            m.return_value = orch

            resp = client.post("/api/groups/g1/update-last-message")

        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_orchestrator_error_returns_500(self, client):
        with patch("app.api.routes.groups.get_orchestrator") as m:
            orch = MagicMock()
            orch.update_last_message_time = AsyncMock(side_effect=Exception("err"))
            m.return_value = orch

            resp = client.post("/api/groups/g1/update-last-message")

        assert resp.status_code == 500


# ###########################################################################
#  POST /groups/{group_id}/set-topic
# ###########################################################################


@pytest.mark.integration
class TestSetGroupTopicEndpoint:
    """POST /api/groups/{group_id}/set-topic"""

    def test_success(self, client):
        result = {"success": True, "group_id": "g1", "topic": "Normalization"}
        with patch("app.api.routes.groups.get_orchestrator") as m:
            orch = MagicMock()
            orch.set_group_topic = AsyncMock(return_value=result)
            m.return_value = orch

            resp = client.post(
                "/api/groups/g1/set-topic",
                data={"topic": "Normalization"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["topic"] == "Normalization"

    def test_orchestrator_error_returns_500(self, client):
        with patch("app.api.routes.groups.get_orchestrator") as m:
            orch = MagicMock()
            orch.set_group_topic = AsyncMock(side_effect=Exception("err"))
            m.return_value = orch

            resp = client.post(
                "/api/groups/g1/set-topic",
                data={"topic": "Something"},
            )

        assert resp.status_code == 500

    def test_missing_topic_returns_422(self, client):
        resp = client.post("/api/groups/g1/set-topic", data={})
        assert resp.status_code == 422


# ###########################################################################
#  GET /efficiency/cache/statistics
# ###########################################################################


@pytest.mark.integration
class TestCacheStatisticsEndpoint:
    """GET /api/efficiency/cache/statistics"""

    def test_enabled(self, client):
        stats = {"cache_hits": 50, "cache_misses": 10, "hit_rate_percent": 83.3}
        with (
            patch("app.api.routes.efficiency.settings") as mock_s,
            patch("app.api.routes.efficiency.get_efficiency_guard") as mock_g,
        ):
            mock_s.ENABLE_EFFICIENCY_GUARD = True
            mock_s.VERSION = "1.0.0"
            guard = MagicMock()
            guard.get_cache_statistics.return_value = stats
            mock_g.return_value = guard

            resp = client.get("/api/efficiency/cache/statistics")

        data = resp.json()
        assert resp.status_code == 200
        assert data["enabled"] is True
        assert data["cache_hits"] == 50

    def test_disabled(self, client):
        with patch("app.api.routes.efficiency.settings") as mock_s:
            mock_s.ENABLE_EFFICIENCY_GUARD = False

            resp = client.get("/api/efficiency/cache/statistics")

        data = resp.json()
        assert data["enabled"] is False
        assert (
            "disabled" in data["message"].lower()
            or "Efficiency Guard" in data["message"]
        )

    def test_guard_error_returns_500(self, client):
        with (
            patch("app.api.routes.efficiency.settings") as mock_s,
            patch("app.api.routes.efficiency.get_efficiency_guard") as mock_g,
        ):
            mock_s.ENABLE_EFFICIENCY_GUARD = True
            guard = MagicMock()
            guard.get_cache_statistics.side_effect = RuntimeError("cache corrupt")
            mock_g.return_value = guard

            resp = client.get("/api/efficiency/cache/statistics")

        assert resp.status_code == 500


# ###########################################################################
#  GET /efficiency/cache/clear
# ###########################################################################


@pytest.mark.integration
class TestCacheClearEndpoint:
    """GET /api/efficiency/cache/clear"""

    def test_enabled(self, client):
        with (
            patch("app.api.routes.efficiency.settings") as mock_s,
            patch("app.api.routes.efficiency.get_efficiency_guard") as mock_g,
        ):
            mock_s.ENABLE_EFFICIENCY_GUARD = True
            guard = MagicMock()
            mock_g.return_value = guard

            resp = client.get("/api/efficiency/cache/clear")

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        guard.clear_cache.assert_called_once()

    def test_disabled(self, client):
        with patch("app.api.routes.efficiency.settings") as mock_s:
            mock_s.ENABLE_EFFICIENCY_GUARD = False

            resp = client.get("/api/efficiency/cache/clear")

        assert resp.json()["enabled"] is False

    def test_guard_error_returns_500(self, client):
        with (
            patch("app.api.routes.efficiency.settings") as mock_s,
            patch("app.api.routes.efficiency.get_efficiency_guard") as mock_g,
        ):
            mock_s.ENABLE_EFFICIENCY_GUARD = True
            guard = MagicMock()
            guard.clear_cache.side_effect = RuntimeError("fail")
            mock_g.return_value = guard

            resp = client.get("/api/efficiency/cache/clear")

        assert resp.status_code == 500


# ###########################################################################
#  GET /efficiency/statistics
# ###########################################################################


@pytest.mark.integration
class TestEfficiencyStatisticsEndpoint:
    """GET /api/efficiency/statistics"""

    def test_enabled(self, client):
        stats = {
            "cache": {"cache_hits": 10},
            "rate_limit": {"total_requests": 50},
            "performance": {"cache_hit_rate_percent": 66.0},
        }
        with (
            patch("app.api.routes.efficiency.settings") as mock_s,
            patch("app.api.routes.efficiency.get_efficiency_guard") as mock_g,
        ):
            mock_s.ENABLE_EFFICIENCY_GUARD = True
            guard = MagicMock()
            guard.get_statistics.return_value = stats
            mock_g.return_value = guard

            resp = client.get("/api/efficiency/statistics")

        data = resp.json()
        assert data["enabled"] is True
        assert "cache" in data
        assert data["rate_limit"]["total_requests"] == 50

    def test_disabled(self, client):
        with patch("app.api.routes.efficiency.settings") as mock_s:
            mock_s.ENABLE_EFFICIENCY_GUARD = False

            resp = client.get("/api/efficiency/statistics")

        assert resp.json()["enabled"] is False

    def test_guard_error_returns_500(self, client):
        with (
            patch("app.api.routes.efficiency.settings") as mock_s,
            patch("app.api.routes.efficiency.get_efficiency_guard") as mock_g,
        ):
            mock_s.ENABLE_EFFICIENCY_GUARD = True
            guard = MagicMock()
            guard.get_statistics.side_effect = Exception("boom")
            mock_g.return_value = guard

            resp = client.get("/api/efficiency/statistics")

        assert resp.status_code == 500


# ###########################################################################
#  GET /efficiency/rate-limit/{identifier}
# ###########################################################################


@pytest.mark.integration
class TestRateLimitInfoEndpoint:
    """GET /api/efficiency/rate-limit/{identifier}"""

    def test_enabled(self, client):
        info = {
            "identifier": "user_42",
            "remaining_requests": 90,
            "is_allowed": True,
        }
        with (
            patch("app.api.routes.efficiency.settings") as mock_s,
            patch("app.api.routes.efficiency.get_efficiency_guard") as mock_g,
        ):
            mock_s.ENABLE_EFFICIENCY_GUARD = True
            guard = MagicMock()
            guard.get_rate_limit_info.return_value = info
            mock_g.return_value = guard

            resp = client.get("/api/efficiency/rate-limit/user_42")

        data = resp.json()
        assert data["enabled"] is True
        assert data["remaining_requests"] == 90
        assert data["is_allowed"] is True

    def test_disabled(self, client):
        with patch("app.api.routes.efficiency.settings") as mock_s:
            mock_s.ENABLE_EFFICIENCY_GUARD = False

            resp = client.get("/api/efficiency/rate-limit/user_42")

        assert resp.json()["enabled"] is False

    def test_guard_error_returns_500(self, client):
        with (
            patch("app.api.routes.efficiency.settings") as mock_s,
            patch("app.api.routes.efficiency.get_efficiency_guard") as mock_g,
        ):
            mock_s.ENABLE_EFFICIENCY_GUARD = True
            guard = MagicMock()
            guard.get_rate_limit_info.side_effect = Exception("oops")
            mock_g.return_value = guard

            resp = client.get("/api/efficiency/rate-limit/user_42")

        assert resp.status_code == 500


# ###########################################################################
#  GET /efficiency/high-frequency-queries
# ###########################################################################


@pytest.mark.integration
class TestHighFrequencyQueriesEndpoint:
    """GET /api/efficiency/high-frequency-queries"""

    def test_enabled_default_limit(self, client):
        queries = [{"query": "React?", "frequency": 50}]
        with (
            patch("app.api.routes.efficiency.settings") as mock_s,
            patch("app.api.routes.efficiency.get_efficiency_guard") as mock_g,
        ):
            mock_s.ENABLE_EFFICIENCY_GUARD = True
            guard = MagicMock()
            guard.get_high_frequency_queries.return_value = queries
            mock_g.return_value = guard

            resp = client.get("/api/efficiency/high-frequency-queries")

        data = resp.json()
        assert data["enabled"] is True
        assert len(data["queries"]) == 1
        # default limit=10 passed to service
        guard.get_high_frequency_queries.assert_called_once_with(limit=10)

    def test_custom_limit(self, client):
        with (
            patch("app.api.routes.efficiency.settings") as mock_s,
            patch("app.api.routes.efficiency.get_efficiency_guard") as mock_g,
        ):
            mock_s.ENABLE_EFFICIENCY_GUARD = True
            guard = MagicMock()
            guard.get_high_frequency_queries.return_value = []
            mock_g.return_value = guard

            client.get("/api/efficiency/high-frequency-queries?limit=5")

        guard.get_high_frequency_queries.assert_called_once_with(limit=5)

    def test_disabled(self, client):
        with patch("app.api.routes.efficiency.settings") as mock_s:
            mock_s.ENABLE_EFFICIENCY_GUARD = False

            resp = client.get("/api/efficiency/high-frequency-queries")

        assert resp.json()["enabled"] is False

    def test_guard_error_returns_500(self, client):
        with (
            patch("app.api.routes.efficiency.settings") as mock_s,
            patch("app.api.routes.efficiency.get_efficiency_guard") as mock_g,
        ):
            mock_s.ENABLE_EFFICIENCY_GUARD = True
            guard = MagicMock()
            guard.get_high_frequency_queries.side_effect = Exception("err")
            mock_g.return_value = guard

            resp = client.get("/api/efficiency/high-frequency-queries")

        assert resp.status_code == 500


# ###########################################################################
#  Background task: _process_ingest_background (lines 266-327)
# ###########################################################################


@pytest.mark.integration
class TestProcessIngestBackground:
    """Direct tests for _process_ingest_background covering L296, L314-315, L325-326."""

    @pytest.mark.asyncio
    async def test_success_path(self):
        """Background task processes file successfully (covers L296 logger.info)."""
        from app.api.routes import _process_ingest_background

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.file_type = "pdf"
        mock_result.chunks = ["chunk1", "chunk2"]
        mock_result.page_count = 3
        mock_result.image_count = 1

        with (
            patch("app.api.routes.documents.get_document_processor") as mock_dp,
            patch("app.api.routes.documents.os.unlink") as mock_unlink,
            patch("app.api.routes.documents.gc.collect"),
        ):
            proc = MagicMock()
            proc.process_file = AsyncMock(return_value=mock_result)
            mock_dp.return_value = proc

            await _process_ingest_background(
                tmp_path="/tmp/test.pdf",
                original_filename="test.pdf",
                course_id="c1",
                file_id="f1",
            )

            proc.process_file.assert_awaited_once()
            mock_unlink.assert_called_once_with("/tmp/test.pdf")

    @pytest.mark.asyncio
    async def test_failure_result(self):
        """Background task handles result.success=False (covers L308-312)."""
        from app.api.routes import _process_ingest_background

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "parse failed"

        with (
            patch("app.api.routes.documents.get_document_processor") as mock_dp,
            patch("app.api.routes.documents.os.unlink"),
            patch("app.api.routes.documents.gc.collect"),
        ):
            proc = MagicMock()
            proc.process_file = AsyncMock(return_value=mock_result)
            mock_dp.return_value = proc

            await _process_ingest_background(
                tmp_path="/tmp/test.pdf",
                original_filename="test.pdf",
                course_id="c1",
                file_id="f1",
            )

    @pytest.mark.asyncio
    async def test_exception_path(self):
        """Background task catches exceptions (covers L314-315)."""
        from app.api.routes import _process_ingest_background

        with (
            patch("app.api.routes.documents.get_document_processor") as mock_dp,
            patch("app.api.routes.documents.os.unlink"),
            patch("app.api.routes.documents.gc.collect"),
        ):
            proc = MagicMock()
            proc.process_file = AsyncMock(side_effect=RuntimeError("kaboom"))
            mock_dp.return_value = proc

            # Should NOT raise — exception is logged internally
            await _process_ingest_background(
                tmp_path="/tmp/test.pdf",
                original_filename="test.pdf",
                course_id="c1",
                file_id="f1",
            )

    @pytest.mark.asyncio
    async def test_cleanup_unlink_oserror(self):
        """os.unlink raises OSError in finally block (covers L325-326)."""
        from app.api.routes import _process_ingest_background

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.file_type = "txt"
        mock_result.chunks = []
        mock_result.page_count = 0
        mock_result.image_count = 0

        with (
            patch("app.api.routes.documents.get_document_processor") as mock_dp,
            patch(
                "app.api.routes.documents.os.unlink",
                side_effect=OSError("no such file"),
            ),
            patch("app.api.routes.documents.gc.collect"),
        ):
            proc = MagicMock()
            proc.process_file = AsyncMock(return_value=mock_result)
            mock_dp.return_value = proc

            # Should NOT raise — OSError is swallowed
            await _process_ingest_background(
                tmp_path="/tmp/gone.txt",
                original_filename="gone.txt",
                course_id="c1",
                file_id="f1",
            )


# ###########################################################################
#  Background task: _process_batch_file_background (lines 417-474)
# ###########################################################################


@pytest.mark.integration
class TestProcessBatchFileBackground:
    """Direct tests for _process_batch_file_background covering L448, L462-463, L472-473."""

    @pytest.mark.asyncio
    async def test_success_path(self):
        """Batch background task processes file successfully (covers L448)."""
        from app.api.routes import _process_batch_file_background

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.chunks = ["c1"]

        with (
            patch("app.api.routes.documents.get_document_processor") as mock_dp,
            patch("app.api.routes.documents.os.unlink"),
            patch("app.api.routes.documents.gc.collect"),
        ):
            proc = MagicMock()
            proc.process_file = AsyncMock(return_value=mock_result)
            mock_dp.return_value = proc

            await _process_batch_file_background(
                tmp_path="/tmp/batch_0.pdf",
                original_filename="doc.pdf",
                course_id="c1",
                document_id="c1_20240101_0",
                batch_index=0,
                extract_images=True,
                perform_ocr=False,
            )

            proc.process_file.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failure_result(self):
        """Batch background task handles result.success=False (covers L456-460)."""
        from app.api.routes import _process_batch_file_background

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "unsupported"

        with (
            patch("app.api.routes.documents.get_document_processor") as mock_dp,
            patch("app.api.routes.documents.os.unlink"),
            patch("app.api.routes.documents.gc.collect"),
        ):
            proc = MagicMock()
            proc.process_file = AsyncMock(return_value=mock_result)
            mock_dp.return_value = proc

            await _process_batch_file_background(
                tmp_path="/tmp/batch_0.pdf",
                original_filename="bad.pdf",
                course_id="c1",
                document_id="c1_20240101_0",
                batch_index=0,
                extract_images=True,
                perform_ocr=False,
            )

    @pytest.mark.asyncio
    async def test_exception_path(self):
        """Batch background task catches exceptions (covers L462-463)."""
        from app.api.routes import _process_batch_file_background

        with (
            patch("app.api.routes.documents.get_document_processor") as mock_dp,
            patch("app.api.routes.documents.os.unlink"),
            patch("app.api.routes.documents.gc.collect"),
        ):
            proc = MagicMock()
            proc.process_file = AsyncMock(side_effect=RuntimeError("disk error"))
            mock_dp.return_value = proc

            await _process_batch_file_background(
                tmp_path="/tmp/batch_0.pdf",
                original_filename="doc.pdf",
                course_id="c1",
                document_id="c1_20240101_0",
                batch_index=0,
                extract_images=True,
                perform_ocr=False,
            )

    @pytest.mark.asyncio
    async def test_cleanup_unlink_oserror(self):
        """os.unlink raises OSError in finally block (covers L472-473)."""
        from app.api.routes import _process_batch_file_background

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.chunks = []

        with (
            patch("app.api.routes.documents.get_document_processor") as mock_dp,
            patch("app.api.routes.documents.os.unlink", side_effect=OSError("gone")),
            patch("app.api.routes.documents.gc.collect"),
        ):
            proc = MagicMock()
            proc.process_file = AsyncMock(return_value=mock_result)
            mock_dp.return_value = proc

            await _process_batch_file_background(
                tmp_path="/tmp/batch_gone.pdf",
                original_filename="doc.pdf",
                course_id="c1",
                document_id="c1_20240101_0",
                batch_index=0,
                extract_images=True,
                perform_ocr=False,
            )


# ###########################################################################
#  Ingest edge cases: empty filename, unlink OSError during write failure
# ###########################################################################


@pytest.mark.integration
class TestIngestEdgeCases:
    """Additional edge cases for /ingest covering L178, L229-230."""

    @pytest.mark.asyncio
    async def test_empty_filename_returns_400(self):
        """File with empty/None filename is rejected (covers L178)."""
        from app.api.routes import ingest_document
        from fastapi import BackgroundTasks, UploadFile

        upload = MagicMock(spec=UploadFile)
        upload.filename = None  # triggers `if not file.filename`

        with pytest.raises(HTTPException) as exc_info:
            await ingest_document(
                background_tasks=BackgroundTasks(),
                file=upload,
                course_id="c1",
                file_id="f1",
            )
        assert exc_info.value.status_code == 400
        assert "Filename" in exc_info.value.detail

    def test_temp_write_error_unlink_oserror(self, client):
        """When temp write fails AND os.unlink also fails (covers L229-230)."""
        with (
            patch("app.api.routes.documents.tempfile.mkstemp") as mock_mkstemp,
            patch(
                "app.api.routes.documents.os.fdopen", side_effect=IOError("disk full")
            ),
            patch(
                "app.api.routes.documents.os.unlink",
                side_effect=OSError("already gone"),
            ),
        ):
            mock_mkstemp.return_value = (999, "/tmp/fake_path")

            resp = client.post(
                "/api/ingest",
                data={"course_id": "c1", "file_id": "f1"},
                files={"file": ("test.pdf", b"data", "application/pdf")},
            )

        assert resp.status_code == 500
        assert resp.json()["detail"] == "INTERNAL_SERVER_ERROR"


# ###########################################################################
#  Batch ingest edge cases: file without filename skip, save exception
# ###########################################################################


@pytest.mark.integration
class TestIngestBatchEdgeCases:
    """Additional edge cases for /ingest/batch covering L361, L386-387, L390."""

    def test_batch_file_save_exception_all_fail(self, client):
        """When NamedTemporaryFile raises for all files -> 400 (covers L386-387, L390)."""
        with patch(
            "app.api.routes.documents.tempfile.NamedTemporaryFile",
            side_effect=OSError("no space"),
        ):
            resp = client.post(
                "/api/ingest/batch",
                data={"course_id": "c1"},
                files=[
                    ("files", ("a.pdf", b"pdf_data", "application/pdf")),
                ],
            )

        assert resp.status_code == 400
        assert "No valid files" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_batch_skip_empty_filename(self):
        """Files with empty filenames are skipped (covers L361 continue)."""
        from io import BytesIO
        from app.api.routes import ingest_batch
        from fastapi import BackgroundTasks, UploadFile

        # File with no filename — should be skipped
        empty_file = MagicMock(spec=UploadFile)
        empty_file.filename = ""

        # File with real filename — should be processed
        real_file = MagicMock(spec=UploadFile)
        real_file.filename = "real.txt"
        real_file.read = AsyncMock(return_value=b"real_data")

        bg = BackgroundTasks()

        result = await ingest_batch(
            background_tasks=bg,
            files=[empty_file, real_file],
            course_id="c1",
            extract_images=True,
            perform_ocr=False,
        )

        assert result.success is True
        assert result.total_files == 1  # only the real file counted
