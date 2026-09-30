import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock heavier modules before anything
sys.modules["chromadb"] = MagicMock()
sys.modules["chromadb.config"] = MagicMock()
sys.modules["chromadb.utils"] = MagicMock()
sys.modules["hnswlib"] = MagicMock()
sys.modules["pypdf"] = MagicMock()
sys.modules["fitz"] = MagicMock()
sys.modules["docx"] = MagicMock()
sys.modules["pptx"] = MagicMock()
sys.modules["openpyxl"] = MagicMock()
sys.modules["pandas"] = MagicMock()
sys.modules["PIL"] = MagicMock()
sys.modules["motor"] = MagicMock()
sys.modules["motor.motor_asyncio"] = MagicMock()
sys.modules["redis.asyncio"] = MagicMock()
sys.modules["redis"] = MagicMock()
sys.modules["prometheus_client"] = MagicMock()

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.core.error_handlers import (
    http_exception_handler,
    validation_exception_handler,
    ExceptionMiddleware,
)

app = FastAPI()
app.include_router(router)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_middleware(ExceptionMiddleware)
client = TestClient(app, raise_server_exceptions=False)


def make_llm_response(content: str, tokens: int = 123):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(total_tokens=tokens),
    )


async def make_stream(chunks):
    for content in chunks:
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
        )


def make_orchestration_result(**overrides):
    data = {
        "success": True,
        "reply": "Bot reply",
        "intervention": None,
        "intervention_type": None,
        "action_taken": "FETCH",
        "should_notify_teacher": False,
        "quality_score": 0.92,
        "analytics": {"source": "test"},
        "error": None,
        "citations": [],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_intervention_result(**overrides):
    data = {
        "success": True,
        "should_intervene": True,
        "message": "Intervene now",
        "intervention_type": SimpleNamespace(value="redirect"),
        "confidence": 0.88,
        "reason": "off-topic",
        "error": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


@patch("app.api.routes.chat.get_rag_pipeline")
def test_ask_question_success_without_sources(mock_rag):
    mock_pipeline = MagicMock()
    mock_result = MagicMock(success=True, answer="Jawaban ringkas", sources=[])
    mock_pipeline.query = AsyncMock(return_value=mock_result)
    mock_rag.return_value = mock_pipeline

    response = client.post("/ask", json={"query": "apa itu ai?", "course_id": "if101"})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["answer"] == "Jawaban ringkas"


@patch("app.api.routes.chat.get_rag_pipeline")
def test_ask_question_invalid_course_id_returns_safe_failure(mock_rag):
    response = client.post("/ask", json={"query": "tes", "course_id": "bad id!"})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "Maaf, terjadi kesalahan" in data["answer"]
    mock_rag.assert_not_called()


@patch("app.api.routes.chat.get_rag_pipeline")
def test_ask_question_pipeline_exception(mock_rag):
    mock_pipeline = MagicMock()
    mock_pipeline.query = AsyncMock(side_effect=Exception("rag down"))
    mock_rag.return_value = mock_pipeline

    response = client.post("/ask", json={"query": "tes", "course_id": "if101"})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["error"] == "Internal error"


@patch("app.api.routes.chat.get_llm_service")
def test_personal_chat_success(mock_get_llm):
    mock_llm = MagicMock()
    mock_llm.ensure_ready = AsyncMock()
    mock_llm.model = "gpt-test"
    mock_llm.client.chat.completions.create = AsyncMock(
        return_value=make_llm_response("Halo juga", 77)
    )
    mock_get_llm.return_value = mock_llm

    payload = {
        "message": "Halo",
        "history": [{"role": "user", "content": "Hai sebelumnya"}],
        "user_name": "Budi",
    }
    response = client.post("/chat/personal", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["reply"] == "Halo juga"
    assert data["tokens_used"] == 0


@patch("app.api.routes.chat.settings")
@patch("app.api.routes.chat.get_llm_service")
def test_personal_chat_forwards_provider_context(mock_get_llm, mock_settings):
    mock_settings.UNIFIED_PROVIDER_ENABLED = True
    mock_settings.UNIFIED_PROVIDER_PERSONAL_CHAT = True

    mock_llm = MagicMock()
    mock_llm.ensure_ready = AsyncMock()
    mock_llm.model = "gpt-test"
    mock_llm.client.chat.completions.create = AsyncMock(
        return_value=make_llm_response("Halo juga", 77)
    )
    mock_get_llm.return_value = mock_llm

    payload = {
        "message": "Halo",
        "history": [],
        "provider_context": {
            "version": "1.0",
            "provider": {"name": "openai", "displayName": "OpenAI GPT"},
            "execution": {
                "baseUrl": "https://provider.example/v1",
                "model": "gpt-4o-mini",
            },
            "auth": {"type": "api-key", "credential": "sk-provider-key"},
            "metadata": {
                "featureFamily": "personal_chat",
                "requestId": "req-1",
                "resolvedAt": "2026-06-16T00:00:00.000Z",
            },
        },
    }
    response = client.post("/chat/personal", json=payload)

    assert response.status_code == 200
    mock_get_llm.assert_called_once_with(provider_context=payload["provider_context"])


@patch("app.api.routes.chat.settings")
@patch("app.api.routes.chat.get_llm_service")
def test_personal_chat_uses_legacy_path_when_feature_flag_disabled(
    mock_get_llm, mock_settings
):
    mock_settings.UNIFIED_PROVIDER_ENABLED = True
    mock_settings.UNIFIED_PROVIDER_PERSONAL_CHAT = False

    mock_llm = MagicMock()
    mock_llm.ensure_ready = AsyncMock()
    mock_llm.model = "gpt-test"
    mock_llm.client.chat.completions.create = AsyncMock(
        return_value=make_llm_response("Halo juga", 77)
    )
    mock_get_llm.return_value = mock_llm

    payload = {
        "message": "Halo",
        "history": [],
        "provider_context": {
            "version": "1.0",
            "provider": {"name": "openai", "displayName": "OpenAI GPT"},
            "execution": {
                "baseUrl": "https://provider.example/v1",
                "model": "gpt-4o-mini",
            },
            "auth": {"type": "api-key", "credential": "sk-provider-key"},
            "metadata": {
                "featureFamily": "personal_chat",
                "requestId": "req-1",
                "resolvedAt": "2026-06-16T00:00:00.000Z",
            },
        },
    }

    response = client.post("/chat/personal", json=payload)

    assert response.status_code == 200
    call_kwargs = mock_get_llm.call_args
    assert call_kwargs[1].get("provider_context") is not None or (
        call_kwargs.args and call_kwargs.args[0] is not None
    )


@patch("app.api.routes.chat.get_llm_service")
def test_personal_chat_failure(mock_get_llm):
    mock_llm = MagicMock()
    mock_llm.ensure_ready = AsyncMock()
    mock_llm.model = "gpt-test"
    mock_llm.client.chat.completions.create = AsyncMock(
        side_effect=Exception("llm failed")
    )
    mock_get_llm.return_value = mock_llm

    response = client.post("/chat/personal", json={"message": "Halo", "history": []})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["reply"].startswith("Maaf")
    assert data["error"] == "Internal error"


@patch("app.api.routes.chat.get_llm_service")
def test_personal_chat_stream_success(mock_get_llm):
    mock_llm = MagicMock()
    mock_llm.ensure_ready = AsyncMock()
    mock_llm.model = "gpt-test"
    mock_llm.client.chat.completions.create = AsyncMock(
        return_value=make_stream(["Halo", " dunia"])
    )
    mock_get_llm.return_value = mock_llm

    response = client.post(
        "/chat/personal/stream", json={"message": "Halo", "history": []}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'data: {"content": "Halo"}' in response.text
    assert "data: [DONE]" in response.text


@patch("app.api.routes.chat.get_llm_service")
def test_personal_chat_stream_failure_event(mock_get_llm):
    mock_llm = MagicMock()
    mock_llm.ensure_ready = AsyncMock()
    mock_llm.model = "gpt-test"
    mock_llm.client.chat.completions.create = AsyncMock(
        side_effect=Exception("stream failed")
    )
    mock_get_llm.return_value = mock_llm

    response = client.post(
        "/chat/personal/stream", json={"message": "Halo", "history": []}
    )

    assert response.status_code == 200
    assert "Internal error" in response.text
    assert "data:" in response.text


@patch("app.api.routes.documents._process_ingest_background", new_callable=AsyncMock)
def test_ingest_document_success(mock_background_task):
    response = client.post(
        "/ingest",
        data={"course_id": "if101", "file_id": "file-1"},
        files={"file": ("materi.txt", b"konten singkat", "text/plain")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["file_id"] == "file-1"
    assert data["file_type"] == "txt"
    mock_background_task.assert_awaited_once()


@patch("app.api.routes.documents._process_ingest_background", new_callable=AsyncMock)
def test_ingest_document_rejects_unsupported_extension(mock_background_task):
    response = client.post(
        "/ingest",
        data={"course_id": "if101", "file_id": "file-2"},
        files={"file": ("script.exe", b"binary", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["message"]
    mock_background_task.assert_not_awaited()


@patch.object(
    __import__("app.api.routes", fromlist=["settings"]).settings,
    "MAX_UPLOAD_SIZE_MB",
    0,
)
@patch("app.api.routes.documents._process_ingest_background", new_callable=AsyncMock)
def test_ingest_document_rejects_oversized_file(mock_background_task):
    response = client.post(
        "/ingest",
        data={"course_id": "if101", "file_id": "file-3"},
        files={"file": ("materi.txt", b"x", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "File size exceeds limit"
    assert response.json()["detail"] == "REQUEST_ERROR"
    mock_background_task.assert_not_awaited()


@patch(
    "app.api.routes.documents._process_batch_file_background", new_callable=AsyncMock
)
def test_ingest_batch_success(mock_background_task):
    response = client.post(
        "/ingest/batch",
        data={"course_id": "if101", "extract_images": "true", "perform_ocr": "false"},
        files=[
            ("files", ("a.txt", b"alpha", "text/plain")),
            ("files", ("b.md", b"beta", "text/markdown")),
        ],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total_files"] == 2
    assert "2 dokumen sedang diproses" in data["message"]
    assert mock_background_task.await_count == 2


@patch(
    "app.api.routes.documents.tempfile.NamedTemporaryFile",
    side_effect=Exception("disk full"),
)
def test_ingest_batch_returns_400_when_no_valid_files(mock_tempfile):
    response = client.post(
        "/ingest/batch",
        data={"course_id": "if101", "extract_images": "true", "perform_ocr": "false"},
        files=[("files", ("a.txt", b"alpha", "text/plain"))],
    )

    assert response.status_code == 400
    assert response.json()["message"] == "No valid files provided"
    assert response.json()["detail"] == "REQUEST_ERROR"
    mock_tempfile.assert_called_once()


@patch("app.api.routes.goals.get_orchestrator")
def test_validate_goal_success(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.validate_goal = AsyncMock(
        return_value={"is_valid": True, "score": 0.9, "feedback": "bagus"}
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post(
        "/goals/validate",
        data={
            "goal_text": "Belajar AI minggu ini",
            "user_id": "u1",
            "session_discussion_id": "c1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is True
    assert data["score"] == 0.9


@patch("app.api.routes.goals.get_orchestrator")
def test_validate_goal_failure(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.validate_goal = AsyncMock(
        side_effect=Exception("service unavailable")
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post(
        "/goals/validate",
        data={"goal_text": "Belajar AI", "user_id": "u1", "session_discussion_id": "c1"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch("app.api.routes.goals.get_orchestrator")
def test_goal_refinement_success(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.get_goal_refinement = AsyncMock(
        return_value={"success": True, "hint": "Tambahkan target terukur"}
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post(
        "/goals/refine",
        data={
            "current_goal": "Mau jago AI",
            "missing_criteria": '["specific", "measurable"]',
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "hint" in data


@patch("app.api.routes.goals.get_orchestrator")
def test_goal_refinement_invalid_json(mock_get_orchestrator):
    response = client.post(
        "/goals/refine",
        data={"current_goal": "Mau jago AI", "missing_criteria": "not-json"},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "Invalid JSON format for missing_criteria"
    assert response.json()["detail"] == "REQUEST_ERROR"
    mock_get_orchestrator.assert_not_called()


@patch("app.api.routes.goals.get_orchestrator")
def test_goal_refinement_failure(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.get_goal_refinement = AsyncMock(
        side_effect=Exception("llm timeout")
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post(
        "/goals/refine",
        data={"current_goal": "Mau jago AI", "missing_criteria": '["time-bound"]'},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch("app.api.routes.groups.get_orchestrator")
def test_check_group_status_success(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    # Synchronous contract: the real orchestrator method is NOT a coroutine;
    # mocking it as AsyncMock hid a production await-TypeError -> 500.
    mock_orchestrator.check_group_status = MagicMock(
        return_value={"should_intervene": True, "interventions": ["prompt"]}
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.get("/groups/group-1/status", params={"topic": "AI ethics"})

    assert response.status_code == 200
    assert response.json()["should_intervene"] is True


@patch("app.api.routes.groups.get_orchestrator")
def test_track_participation_success(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.track_participation = AsyncMock(
        return_value={"success": True, "tracked": True}
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post(
        "/groups/group-1/track-participation", data={"user_id": "user-1"}
    )

    assert response.status_code == 200
    assert response.json()["tracked"] is True


@patch("app.api.routes.groups.get_orchestrator")
def test_update_last_message_time_success(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.update_last_message_time = AsyncMock(
        return_value={"success": True, "updated": True}
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post("/groups/group-1/update-last-message")

    assert response.status_code == 200
    assert response.json()["updated"] is True


@patch("app.api.routes.groups.get_orchestrator")
def test_set_group_topic_success(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.set_group_topic = AsyncMock(
        return_value={"success": True, "topic": "AI ethics"}
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post("/groups/group-1/set-topic", data={"topic": "AI ethics"})

    assert response.status_code == 200
    assert response.json()["topic"] == "AI ethics"


@patch.object(
    __import__("app.api.routes", fromlist=["settings"]).settings,
    "ENABLE_EFFICIENCY_GUARD",
    True,
)
@patch("app.api.routes.efficiency.get_efficiency_guard")
def test_get_cache_statistics_enabled(mock_get_guard):
    mock_guard = MagicMock()
    mock_guard.get_cache_statistics.return_value = {
        "cache_hits": 10,
        "cache_misses": 5,
        "hit_rate_percent": 66.7,
    }
    mock_get_guard.return_value = mock_guard

    response = client.get("/efficiency/cache/statistics")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["cache_hits"] == 10


@patch.object(
    __import__("app.api.routes", fromlist=["settings"]).settings,
    "ENABLE_EFFICIENCY_GUARD",
    False,
)
def test_get_cache_statistics_disabled():
    response = client.get("/efficiency/cache/statistics")

    assert response.status_code == 200
    assert response.json()["enabled"] is False


@patch.object(
    __import__("app.api.routes", fromlist=["settings"]).settings,
    "ENABLE_EFFICIENCY_GUARD",
    True,
)
@patch("app.api.routes.efficiency.get_efficiency_guard")
def test_clear_cache_success(mock_get_guard):
    mock_guard = MagicMock()
    mock_get_guard.return_value = mock_guard

    response = client.get("/efficiency/cache/clear")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    mock_guard.clear_cache.assert_called_once()


@patch.object(
    __import__("app.api.routes", fromlist=["settings"]).settings,
    "ENABLE_EFFICIENCY_GUARD",
    True,
)
@patch("app.api.routes.efficiency.get_efficiency_guard")
def test_get_efficiency_statistics_enabled(mock_get_guard):
    mock_guard = MagicMock()
    mock_guard.get_statistics.return_value = {
        "rate_limit": {"total_requests": 12},
        "performance": {"cache_hit_rate_percent": 75.0},
    }
    mock_get_guard.return_value = mock_guard

    response = client.get("/efficiency/statistics")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["rate_limit"]["total_requests"] == 12


@patch.object(
    __import__("app.api.routes", fromlist=["settings"]).settings,
    "ENABLE_EFFICIENCY_GUARD",
    True,
)
@patch("app.api.routes.efficiency.get_efficiency_guard")
def test_get_rate_limit_info_enabled(mock_get_guard):
    mock_guard = MagicMock()
    mock_guard.get_rate_limit_info.return_value = {
        "remaining_requests": 4,
        "is_allowed": True,
    }
    mock_get_guard.return_value = mock_guard

    response = client.get("/efficiency/rate-limit/user-1")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["remaining_requests"] == 4


@patch.object(
    __import__("app.api.routes", fromlist=["settings"]).settings,
    "ENABLE_EFFICIENCY_GUARD",
    True,
)
@patch("app.api.routes.efficiency.get_efficiency_guard")
def test_get_high_frequency_queries_enabled(mock_get_guard):
    mock_guard = MagicMock()
    mock_guard.get_high_frequency_queries.return_value = [
        {"query": "apa itu ai?", "count": 8},
        {"query": "contoh ml", "count": 5},
    ]
    mock_get_guard.return_value = mock_guard

    response = client.get("/efficiency/high-frequency-queries", params={"limit": 2})

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert len(data["queries"]) == 2


@patch("app.api.routes.monitoring.get_monitor")
def test_metrics_success(mock_get_monitor):
    mock_monitor = MagicMock()
    mock_monitor.get_metrics.return_value = "requests_total 1\n"
    mock_monitor.get_content_type.return_value = "text/plain; version=0.0.4"
    mock_get_monitor.return_value = mock_monitor

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.text == "requests_total 1\n"
    assert response.headers["content-type"].startswith("text/plain")


@patch("app.api.routes.monitoring.get_monitor")
def test_monitoring_status_success(mock_get_monitor):
    mock_monitor = MagicMock()
    mock_monitor.get_dashboard_data.return_value = {"status": "ok", "uptime": 100}
    mock_get_monitor.return_value = mock_monitor

    response = client.get("/health/monitoring")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@patch("app.api.routes.monitoring.get_llm_circuit_breaker")
def test_get_circuit_breaker_status_success(mock_get_cb):
    mock_cb = MagicMock()
    mock_cb.get_metrics.return_value = {"state": "closed", "failures": 0}
    mock_get_cb.return_value = mock_cb

    response = client.get("/health/circuit-breakers")

    assert response.status_code == 200
    data = response.json()
    assert data["llm_service"]["state"] == "closed"


@patch("app.api.routes.monitoring.get_reranker")
def test_get_reranker_status_success(mock_get_reranker):
    mock_reranker = MagicMock()
    mock_reranker.get_metrics.return_value = {"enabled": True, "model": "cross-encoder"}
    mock_get_reranker.return_value = mock_reranker

    response = client.get("/health/reranker")

    assert response.status_code == 200
    assert response.json()["enabled"] is True


@patch("app.api.routes.analytics.get_export_service")
def test_export_group_activity_csv_success(mock_get_export_service):
    mock_service = MagicMock()
    mock_service.export_group_activity_detailed = AsyncMock(
        return_value="name,count\nA,1\n"
    )
    mock_get_export_service.return_value = mock_service

    response = client.get("/export/activity/group/group-1")

    assert response.status_code == 200
    assert response.text == "name,count\nA,1\n"
    assert response.headers["content-type"].startswith("text/csv")


@patch("app.api.routes.analytics.get_export_service")
def test_export_session_discussion_activity_csv_success(mock_get_export_service):
    mock_service = MagicMock()
    mock_service.export_session_discussion_activity = AsyncMock(
        return_value="user,msg\nu1,halo\n"
    )
    mock_get_export_service.return_value = mock_service

    response = client.get(
        "/export/activity/session-discussion/chat-1", params={"include_detailed": "true"}
    )

    assert response.status_code == 200
    assert response.text == "user,msg\nu1,halo\n"
    assert "attachment;" in response.headers["content-disposition"]


@patch("app.services.mongodb_logger.get_mongo_logger")
def test_export_process_mining_case_csv_success(mock_get_mongo_logger):
    mock_logger = MagicMock()
    mock_logger.export_to_csv = AsyncMock(return_value="CaseID,Activity\n1,Start\n")
    mock_get_mongo_logger.return_value = mock_logger

    response = client.get("/export/process-mining/case/case-1")

    assert response.status_code == 200
    assert response.text == "CaseID,Activity\n1,Start\n"
    assert response.headers["content-type"].startswith("text/csv")


@patch("app.api.routes.analytics.get_mongo_logger")
def test_analytics_export_json_success(mock_get_mongo_logger):
    mock_logger = MagicMock()
    mock_logger.export_to_csv = AsyncMock(
        return_value="CaseID,Activity\n1,Start\n1,End\n2,Start\n"
    )
    mock_get_mongo_logger.return_value = mock_logger

    response = client.get("/analytics/export")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total_events"] == 3
    assert data["unique_cases"] == 2


@patch("app.api.routes.analytics.get_mongo_logger")
def test_analytics_export_csv_success(mock_get_mongo_logger):
    mock_logger = MagicMock()
    mock_logger.export_to_csv = AsyncMock(return_value="CaseID,Activity\n1,Start\n")
    mock_get_mongo_logger.return_value = mock_logger

    response = client.get("/analytics/export", params={"format": "csv"})

    assert response.status_code == 200
    assert response.text == "CaseID,Activity\n1,Start\n"
    assert response.headers["content-type"].startswith("text/csv")


@patch("app.api.routes.orchestration.get_orchestrator")
def test_orchestrated_chat_success(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.handle_message = AsyncMock(
        return_value=make_orchestration_result(
            reply="Ini jawaban AI",
            intervention="Coba fokus ke topik",
            intervention_type="redirect",
        )
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    payload = {
        "user_id": "u1",
        "group_id": "g1",
        "message": "Apa itu AI?",
        "topic": "Artificial Intelligence",
        "collection_name": "course_if101",
        "course_id": "if101",
        "chat_room_id": "room-1",
    }
    response = client.post("/chat", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["bot_response"] == "Ini jawaban AI"
    assert data["action_taken"] == "FETCH"


@patch("app.api.routes.orchestration.settings")
@patch("app.api.routes.orchestration.get_orchestrator")
def test_orchestrated_chat_forwards_provider_context(
    mock_get_orchestrator, mock_settings
):
    mock_settings.UNIFIED_PROVIDER_ENABLED = True
    mock_settings.UNIFIED_PROVIDER_ORCHESTRATION = True

    mock_orchestrator = MagicMock()
    mock_orchestrator.handle_message = AsyncMock(
        return_value=make_orchestration_result(reply="Ini jawaban AI")
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    provider_context = {
        "version": "1.0",
        "provider": {"name": "openai", "displayName": "OpenAI GPT"},
        "execution": {"baseUrl": "https://provider.example/v1", "model": "gpt-4o-mini"},
        "auth": {"type": "api-key", "credential": "sk-provider-key"},
        "metadata": {
            "featureFamily": "orchestration",
            "requestId": "req-1",
            "resolvedAt": "2026-06-16T00:00:00.000Z",
        },
    }
    payload = {
        "user_id": "u1",
        "group_id": "g1",
        "message": "Apa itu AI?",
        "provider_context": provider_context,
    }
    response = client.post("/chat", json=payload)

    assert response.status_code == 200
    mock_get_orchestrator.assert_called_once_with(provider_context=provider_context)


@patch("app.api.routes.orchestration.settings")
@patch("app.api.routes.orchestration.get_orchestrator")
def test_orchestrated_chat_uses_legacy_path_when_feature_flag_disabled(
    mock_get_orchestrator, mock_settings
):
    mock_settings.UNIFIED_PROVIDER_ENABLED = True
    mock_settings.UNIFIED_PROVIDER_ORCHESTRATION = False

    mock_orchestrator = MagicMock()
    mock_orchestrator.handle_message = AsyncMock(
        return_value=make_orchestration_result(reply="Ini jawaban AI")
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post(
        "/chat",
        json={
            "user_id": "u1",
            "group_id": "g1",
            "message": "Apa itu AI?",
            "provider_context": {
                "version": "1.0",
                "provider": {"name": "openai", "displayName": "OpenAI GPT"},
                "execution": {
                    "baseUrl": "https://provider.example/v1",
                    "model": "gpt-4o-mini",
                },
                "auth": {"type": "api-key", "credential": "sk-provider-key"},
                "metadata": {
                    "featureFamily": "orchestration",
                    "requestId": "req-1",
                    "resolvedAt": "2026-06-16T00:00:00.000Z",
                },
            },
        },
    )

    assert response.status_code == 200
    call_kwargs = mock_get_orchestrator.call_args
    assert call_kwargs[1].get("provider_context") is not None or (
        call_kwargs.args and call_kwargs.args[0] is not None
    )


@patch("app.api.routes.orchestration.get_orchestrator")
def test_orchestrated_chat_failure(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.handle_message = AsyncMock(
        side_effect=Exception("pipeline error")
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    payload = {"user_id": "u1", "group_id": "g1", "message": "Apa itu AI?"}
    response = client.post("/chat", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["action_taken"] == "ERROR"
    assert data["error"] == "Internal error"


@patch("app.api.routes.interventions.get_intervention_service")
def test_analyze_intervention_success(mock_get_service):
    mock_service = MagicMock()
    mock_service.analyze_and_intervene = AsyncMock(
        return_value=make_intervention_result()
    )
    mock_get_service.return_value = mock_service

    payload = {
        "messages": [
            {
                "sender": "Alice",
                "content": "Mari fokus",
                "timestamp": "2025-01-01T00:00:00",
                "sender_id": "u1",
            }
        ],
        "topic": "AI ethics",
        "chat_room_id": "room-1",
    }
    response = client.post("/intervention/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["should_intervene"] is True
    assert data["intervention_type"] == "redirect"


@patch("app.api.routes.interventions.settings")
@patch("app.api.routes.interventions.get_intervention_service")
def test_analyze_intervention_forwards_provider_context(
    mock_get_service, mock_settings
):
    mock_settings.UNIFIED_PROVIDER_ENABLED = True
    mock_settings.UNIFIED_PROVIDER_INTERVENTIONS = True

    mock_service = MagicMock()
    mock_service.analyze_and_intervene = AsyncMock(
        return_value=make_intervention_result()
    )
    mock_get_service.return_value = mock_service

    provider_context = {
        "version": "1.0",
        "provider": {"name": "openai", "displayName": "OpenAI GPT"},
        "execution": {"baseUrl": "https://provider.example/v1", "model": "gpt-4o-mini"},
        "auth": {"type": "api-key", "credential": "sk-provider-key"},
        "metadata": {
            "featureFamily": "interventions",
            "requestId": "req-1",
            "resolvedAt": "2026-06-16T00:00:00.000Z",
        },
    }
    payload = {
        "messages": [{"sender": "Alice", "content": "Mari fokus"}],
        "topic": "AI ethics",
        "chat_room_id": "room-1",
        "provider_context": provider_context,
    }
    response = client.post("/intervention/analyze", json=payload)

    assert response.status_code == 200
    mock_get_service.assert_called_once_with(provider_context=provider_context)


@patch("app.api.routes.interventions.settings")
@patch("app.api.routes.interventions.get_intervention_service")
def test_analyze_intervention_uses_legacy_path_when_feature_flag_disabled(
    mock_get_service, mock_settings
):
    mock_settings.UNIFIED_PROVIDER_ENABLED = True
    mock_settings.UNIFIED_PROVIDER_INTERVENTIONS = False

    mock_service = MagicMock()
    mock_service.analyze_and_intervene = AsyncMock(
        return_value=make_intervention_result()
    )
    mock_get_service.return_value = mock_service

    response = client.post(
        "/intervention/analyze",
        json={
            "messages": [{"sender": "Alice", "content": "Mari fokus"}],
            "topic": "AI ethics",
            "chat_room_id": "room-1",
            "provider_context": {
                "version": "1.0",
                "provider": {"name": "openai", "displayName": "OpenAI GPT"},
                "execution": {
                    "baseUrl": "https://provider.example/v1",
                    "model": "gpt-4o-mini",
                },
                "auth": {"type": "api-key", "credential": "sk-provider-key"},
                "metadata": {
                    "featureFamily": "interventions",
                    "requestId": "req-1",
                    "resolvedAt": "2026-06-16T00:00:00.000Z",
                },
            },
        },
    )

    assert response.status_code == 200
    call_kwargs = mock_get_service.call_args
    assert call_kwargs[1].get("provider_context") is not None or (
        call_kwargs.args and call_kwargs.args[0] is not None
    )


@patch("app.api.routes.interventions.get_intervention_service")
def test_analyze_intervention_failure(mock_get_service):
    mock_service = MagicMock()
    mock_service.analyze_and_intervene = AsyncMock(
        side_effect=Exception("analysis failed")
    )
    mock_get_service.return_value = mock_service

    payload = {
        "messages": [{"sender": "Alice", "content": "test"}],
        "topic": "AI ethics",
        "chat_room_id": "room-1",
    }
    response = client.post("/intervention/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["error"] == "Internal error"


@patch("app.api.routes.interventions.get_intervention_service")
def test_generate_summary_success(mock_get_service):
    mock_service = MagicMock()
    mock_service.generate_summary = AsyncMock(
        return_value=SimpleNamespace(
            success=True, message="Ringkasan diskusi", error=None
        )
    )
    mock_get_service.return_value = mock_service

    payload = {
        "messages": [
            {"sender": "Alice", "content": "Pesan 1"},
            {"sender": "Bob", "content": "Pesan 2"},
        ],
        "chat_room_id": "room-1",
    }
    response = client.post("/intervention/summary", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["summary"] == "Ringkasan diskusi"
    assert data["message_count"] == 2


@patch("app.api.routes.interventions.get_intervention_service")
def test_generate_prompt_success(mock_get_service):
    mock_service = MagicMock()
    mock_service.generate_discussion_prompt = AsyncMock(
        return_value=SimpleNamespace(success=True, message="Apa dampak AI?", error=None)
    )
    mock_get_service.return_value = mock_service

    response = client.post(
        "/intervention/prompt",
        json={"topic": "AI ethics", "context": "kelas 1", "difficulty": "medium"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["prompt"] == "Apa dampak AI?"
    assert data["topic"] == "AI ethics"


@patch("app.api.routes.analytics.get_orchestrator")
def test_get_group_analytics_alias_success(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.get_group_dashboard_data = AsyncMock(
        return_value={
            "message_count": 20,
            "quality_score": 0.85,
            "quality_breakdown": {"clarity": 0.8},
            "recommendation": "Pertahankan diskusi",
            "participants": ["u1", "u2"],
            "participant_count": 2,
            "engagement_distribution": {"high": 2},
            "hot_percentage": 70.0,
        }
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.get("/analytics/group/group-1")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["group_id"] == "group-1"
    assert data["participant_count"] == 2


@patch("app.api.routes.documents.get_vector_store")
def test_delete_document_success(mock_get_vector_store):
    mock_store = MagicMock()
    mock_store.delete_documents = AsyncMock()
    mock_get_vector_store.return_value = mock_store

    response = client.delete(
        "/documents/doc-1", params={"collection_name": "course_if101"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "doc-1" in data["message"]


@patch("app.api.routes.documents.get_vector_store")
def test_delete_document_failure(mock_get_vector_store):
    mock_store = MagicMock()
    mock_store.delete_documents = AsyncMock(side_effect=Exception("delete failed"))
    mock_get_vector_store.return_value = mock_store

    response = client.delete("/documents/doc-1")

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch("app.api.routes.analytics.get_engagement_analyzer")
def test_analyze_engagement_failure(mock_get_analyzer):
    mock_analyzer = MagicMock()
    mock_analyzer.analyze_interaction.side_effect = Exception("nlp failed")
    mock_get_analyzer.return_value = mock_analyzer

    response = client.post("/analytics/engagement", json={"text": "tes engagement"})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["engagement_type"] == "unknown"
    assert data["error"] == "Internal error"


@patch("app.api.routes.chat.get_rag_pipeline")
def test_ask_question_success_with_sources_without_page(mock_rag):
    mock_pipeline = MagicMock()
    mock_result = MagicMock(
        success=True,
        answer="Jawaban lengkap",
        sources=[{"source": "Modul AI"}],
    )
    mock_pipeline.query = AsyncMock(return_value=mock_result)
    mock_rag.return_value = mock_pipeline

    response = client.post("/ask", json={"query": "jelaskan ai", "course_id": "if101"})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "1. Modul AI" in data["answer"]
    assert "(hal." not in data["answer"]


@patch("app.api.routes.chat.get_llm_service")
def test_personal_chat_stream_includes_history_messages(mock_get_llm):
    mock_llm = MagicMock()
    mock_llm.ensure_ready = AsyncMock()
    mock_llm.model = "gpt-test"
    mock_llm.client.chat.completions.create = AsyncMock(
        return_value=make_stream(["Hai"])
    )
    mock_get_llm.return_value = mock_llm

    payload = {
        "message": "Lanjut",
        "history": [
            {"role": "user", "content": "Halo"},
            {"role": "assistant", "content": "Hai juga"},
        ],
    }
    response = client.post("/chat/personal/stream", json=payload)

    assert response.status_code == 200
    called_messages = mock_llm.client.chat.completions.create.await_args.kwargs[
        "messages"
    ]
    assert called_messages[1] == {"role": "user", "content": "Halo"}
    assert called_messages[2] == {"role": "assistant", "content": "Hai juga"}
    assert 'data: {"content": "Hai"}' in response.text


def test_ingest_document_requires_filename():
    import asyncio
    from io import BytesIO

    from fastapi import BackgroundTasks, HTTPException
    from starlette.datastructures import UploadFile

    from app.api.routes import ingest_document

    upload = UploadFile(file=BytesIO(b"abc"), filename="")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_document(
                background_tasks=BackgroundTasks(),
                file=upload,
                course_id="if101",
                file_id="file-no-name",
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Filename is required"


def test_ingest_document_returns_500_when_temp_write_fails():
    class BrokenWriter:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def write(self, chunk):
            raise RuntimeError("disk write failed")

        def close(self):
            return None

    with patch(
        "app.api.routes.documents.tempfile.mkstemp",
        return_value=(123, "/tmp/fake-upload.txt"),
    ):
        with patch("app.api.routes.documents.os.fdopen", return_value=BrokenWriter()):
            with patch("app.api.routes.documents.os.unlink") as mock_unlink:
                response = client.post(
                    "/ingest",
                    data={"course_id": "if101", "file_id": "file-write-error"},
                    files={"file": ("materi.txt", b"abc", "text/plain")},
                )

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"
    mock_unlink.assert_called_once_with("/tmp/fake-upload.txt")


@patch("app.api.routes.documents.get_document_processor")
def test_process_ingest_background_success(mock_get_processor):
    import asyncio
    import os
    import tempfile

    from app.api.routes import _process_ingest_background

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.write(b"fake pdf")
    tmp.close()

    mock_processor = MagicMock()
    mock_processor.process_file = AsyncMock(
        return_value=SimpleNamespace(
            success=True,
            file_type="pdf",
            chunks=["c1", "c2"],
            page_count=2,
            image_count=0,
            error=None,
        )
    )
    mock_get_processor.return_value = mock_processor

    asyncio.run(
        _process_ingest_background(
            tmp.name,
            "materi.pdf",
            "if101",
            "file-123",
        )
    )

    kwargs = mock_processor.process_file.await_args.kwargs
    assert kwargs["collection_name"] == "course_if101"
    assert kwargs["document_id"] == "file-123"
    assert kwargs["metadata"]["original_filename"] == "materi.pdf"
    assert not os.path.exists(tmp.name)


@patch("app.api.routes.documents.get_document_processor")
def test_process_ingest_background_logs_failed_result_and_cleans_up(mock_get_processor):
    import asyncio
    import os
    import tempfile

    from app.api.routes import _process_ingest_background

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    tmp.write(b"hello")
    tmp.close()

    mock_processor = MagicMock()
    mock_processor.process_file = AsyncMock(
        return_value=SimpleNamespace(
            success=False,
            file_type="txt",
            chunks=[],
            page_count=0,
            image_count=0,
            error="parse failed",
        )
    )
    mock_get_processor.return_value = mock_processor

    asyncio.run(_process_ingest_background(tmp.name, "materi.txt", "if101", "file-err"))

    assert mock_processor.process_file.await_count == 1
    assert not os.path.exists(tmp.name)


@patch("app.api.routes.documents.get_document_processor")
def test_process_ingest_background_handles_exception_and_cleans_up(mock_get_processor):
    import asyncio
    import os
    import tempfile

    from app.api.routes import _process_ingest_background

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
    tmp.write(b"docx")
    tmp.close()

    mock_processor = MagicMock()
    mock_processor.process_file = AsyncMock(side_effect=Exception("processor crashed"))
    mock_get_processor.return_value = mock_processor

    asyncio.run(
        _process_ingest_background(tmp.name, "materi.docx", "if101", "file-boom")
    )

    assert not os.path.exists(tmp.name)


@patch(
    "app.api.routes.documents._process_batch_file_background", new_callable=AsyncMock
)
def test_ingest_batch_skips_entries_without_filename(mock_background_task):
    import asyncio
    from io import BytesIO

    from fastapi import BackgroundTasks
    from starlette.datastructures import UploadFile

    from app.api.routes import ingest_batch

    background_tasks = BackgroundTasks()
    result = asyncio.run(
        ingest_batch(
            background_tasks=background_tasks,
            files=[
                UploadFile(file=BytesIO(b""), filename=""),
                UploadFile(file=BytesIO(b"alpha"), filename="valid.txt"),
            ],
            course_id="if101",
            extract_images=False,
            perform_ocr=False,
        )
    )

    data = result.model_dump()
    assert data["total_files"] == 1
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].func is mock_background_task


@patch("app.api.routes.documents.get_document_processor")
def test_process_batch_file_background_success(mock_get_processor):
    import asyncio
    import os
    import tempfile

    from app.api.routes import _process_batch_file_background

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.write(b"fake pdf")
    tmp.close()

    mock_processor = MagicMock()
    mock_processor.process_file = AsyncMock(
        return_value=SimpleNamespace(
            success=True,
            chunks=["c1"],
            error=None,
        )
    )
    mock_get_processor.return_value = mock_processor

    asyncio.run(
        _process_batch_file_background(
            tmp.name,
            "batch.pdf",
            "if101",
            "doc-1",
            3,
            True,
            False,
        )
    )

    kwargs = mock_processor.process_file.await_args.kwargs
    assert kwargs["collection_name"] == "course_if101"
    assert kwargs["metadata"]["batch_index"] == 3
    assert kwargs["metadata"]["extract_images"] is True
    assert kwargs["metadata"]["perform_ocr"] is False
    assert not os.path.exists(tmp.name)


@patch("app.api.routes.documents.get_document_processor")
def test_process_batch_file_background_handles_failed_result(mock_get_processor):
    import asyncio
    import os
    import tempfile

    from app.api.routes import _process_batch_file_background

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".md")
    tmp.write(b"# test")
    tmp.close()

    mock_processor = MagicMock()
    mock_processor.process_file = AsyncMock(
        return_value=SimpleNamespace(
            success=False, chunks=[], error="batch parse failed"
        )
    )
    mock_get_processor.return_value = mock_processor

    asyncio.run(
        _process_batch_file_background(
            tmp.name,
            "batch.md",
            "if101",
            "doc-2",
            1,
            False,
            True,
        )
    )

    assert mock_processor.process_file.await_count == 1
    assert not os.path.exists(tmp.name)


@patch("app.api.routes.documents.get_document_processor")
def test_process_batch_file_background_handles_exception(mock_get_processor):
    import asyncio
    import os
    import tempfile

    from app.api.routes import _process_batch_file_background

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    tmp.write(b"text")
    tmp.close()

    mock_processor = MagicMock()
    mock_processor.process_file = AsyncMock(side_effect=Exception("batch exploded"))
    mock_get_processor.return_value = mock_processor

    asyncio.run(
        _process_batch_file_background(
            tmp.name,
            "batch.txt",
            "if101",
            "doc-3",
            0,
            False,
            False,
        )
    )

    assert not os.path.exists(tmp.name)


@patch("app.api.routes.health.get_vector_store")
@patch("app.services.llm.get_llm_service", side_effect=Exception("llm unavailable"))
def test_health_check_degraded_when_llm_check_fails(
    mock_get_llm, mock_get_vector_store
):
    mock_store = MagicMock()
    mock_store._ensure_collection = AsyncMock(return_value=None)
    mock_get_vector_store.return_value = mock_store

    response = client.get("/health")

    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["services"]["vector_store"] is True
    assert data["services"]["llm"] is False


@patch("app.api.routes.analytics.get_orchestrator")
def test_group_dashboard_failure_returns_500(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.get_group_dashboard_data = AsyncMock(
        side_effect=Exception("dashboard failed")
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.get("/analytics/dashboard/group/group-1")

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch("app.api.routes.analytics.get_orchestrator")
def test_individual_dashboard_failure_returns_500(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.get_individual_dashboard_data = AsyncMock(
        side_effect=Exception("individual failed")
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.get("/analytics/dashboard/individual/user-1")

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


def test_validate_course_id_rejects_invalid_characters():
    from fastapi import HTTPException

    from app.api.routes.chat import validate_course_id

    with pytest.raises(HTTPException) as exc_info:
        validate_course_id("course/../etc")

    assert exc_info.value.status_code == 400
    assert "Invalid course ID format" in exc_info.value.detail


@patch("app.api.routes.groups.get_orchestrator")
def test_check_group_status_failure(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.check_group_status = MagicMock(
        side_effect=Exception("status down")
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.get("/groups/group-1/status", params={"topic": "AI"})

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch("app.api.routes.groups.get_orchestrator")
def test_track_participation_failure(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.track_participation = AsyncMock(
        side_effect=Exception("tracking failed")
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post(
        "/groups/group-1/track-participation", data={"user_id": "user-1"}
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch("app.api.routes.groups.get_orchestrator")
def test_update_last_message_time_failure(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.update_last_message_time = AsyncMock(
        side_effect=Exception("timestamp failed")
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post("/groups/group-1/update-last-message")

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch("app.api.routes.groups.get_orchestrator")
def test_set_group_topic_failure(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.set_group_topic = AsyncMock(side_effect=Exception("topic failed"))
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.post("/groups/group-1/set-topic", data={"topic": "AI ethics"})

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch.object(
    __import__("app.api.routes", fromlist=["settings"]).settings,
    "ENABLE_EFFICIENCY_GUARD",
    True,
)
@patch("app.api.routes.efficiency.get_efficiency_guard")
def test_get_cache_statistics_failure(mock_get_guard):
    mock_guard = MagicMock()
    mock_guard.get_cache_statistics.side_effect = Exception("cache stats failed")
    mock_get_guard.return_value = mock_guard

    response = client.get("/efficiency/cache/statistics")

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch.object(
    __import__("app.api.routes", fromlist=["settings"]).settings,
    "ENABLE_EFFICIENCY_GUARD",
    True,
)
@patch("app.api.routes.efficiency.get_efficiency_guard")
def test_clear_cache_failure(mock_get_guard):
    mock_guard = MagicMock()
    mock_guard.clear_cache.side_effect = Exception("clear failed")
    mock_get_guard.return_value = mock_guard

    response = client.get("/efficiency/cache/clear")

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch.object(
    __import__("app.api.routes", fromlist=["settings"]).settings,
    "ENABLE_EFFICIENCY_GUARD",
    False,
)
def test_get_efficiency_statistics_disabled():
    response = client.get("/efficiency/statistics")

    assert response.status_code == 200
    assert response.json()["enabled"] is False


@patch.object(
    __import__("app.api.routes", fromlist=["settings"]).settings,
    "ENABLE_EFFICIENCY_GUARD",
    True,
)
@patch("app.api.routes.efficiency.get_efficiency_guard")
def test_get_efficiency_statistics_failure(mock_get_guard):
    mock_guard = MagicMock()
    mock_guard.get_statistics.side_effect = Exception("efficiency stats failed")
    mock_get_guard.return_value = mock_guard

    response = client.get("/efficiency/statistics")

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch.object(
    __import__("app.api.routes", fromlist=["settings"]).settings,
    "ENABLE_EFFICIENCY_GUARD",
    False,
)
def test_get_rate_limit_info_disabled():
    response = client.get("/efficiency/rate-limit/user-1")

    assert response.status_code == 200
    assert response.json()["enabled"] is False


@patch.object(
    __import__("app.api.routes", fromlist=["settings"]).settings,
    "ENABLE_EFFICIENCY_GUARD",
    True,
)
@patch("app.api.routes.efficiency.get_efficiency_guard")
def test_get_rate_limit_info_failure(mock_get_guard):
    mock_guard = MagicMock()
    mock_guard.get_rate_limit_info.side_effect = Exception("rate limit failed")
    mock_get_guard.return_value = mock_guard

    response = client.get("/efficiency/rate-limit/user-1")

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch("app.api.routes.monitoring.get_monitor")
def test_metrics_failure(mock_get_monitor):
    mock_get_monitor.side_effect = Exception("metrics failed")

    response = client.get("/metrics")

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch("app.api.routes.monitoring.get_monitor")
def test_monitoring_status_failure(mock_get_monitor):
    mock_get_monitor.side_effect = Exception("monitor failed")

    response = client.get("/health/monitoring")

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch("app.api.routes.monitoring.get_llm_circuit_breaker")
def test_get_circuit_breaker_status_failure(mock_get_cb):
    mock_get_cb.side_effect = Exception("breaker failed")

    response = client.get("/health/circuit-breakers")

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch("app.api.routes.monitoring.get_reranker")
def test_get_reranker_status_failure(mock_get_reranker):
    mock_get_reranker.side_effect = Exception("reranker failed")

    response = client.get("/health/reranker")

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch("app.api.routes.analytics.get_export_service")
def test_export_group_activity_csv_failure(mock_get_export_service):
    mock_service = MagicMock()
    mock_service.export_group_activity_detailed = AsyncMock(
        side_effect=Exception("export group failed")
    )
    mock_get_export_service.return_value = mock_service

    response = client.get("/export/activity/group/group-1")

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch("app.api.routes.analytics.get_export_service")
def test_export_session_discussion_activity_csv_failure(mock_get_export_service):
    mock_service = MagicMock()
    mock_service.export_session_discussion_activity = AsyncMock(
        side_effect=Exception("export chat failed")
    )
    mock_get_export_service.return_value = mock_service

    response = client.get("/export/activity/session-discussion/chat-1")

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch("app.services.mongodb_logger.get_mongo_logger")
def test_export_process_mining_case_csv_failure(mock_get_mongo_logger):
    mock_logger = MagicMock()
    mock_logger.export_to_csv = AsyncMock(side_effect=Exception("case export failed"))
    mock_get_mongo_logger.return_value = mock_logger

    response = client.get("/export/process-mining/case/case-1")

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch("app.api.routes.interventions.get_intervention_service")
def test_generate_summary_failure(mock_get_service):
    mock_service = MagicMock()
    mock_service.generate_summary = AsyncMock(side_effect=Exception("summary failed"))
    mock_get_service.return_value = mock_service

    payload = {
        "messages": [{"sender": "Alice", "content": "Pesan 1"}],
        "chat_room_id": "room-1",
    }
    response = client.post("/intervention/summary", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["summary"] == ""
    assert data["error"] == "Internal error"


@patch("app.api.routes.interventions.get_intervention_service")
def test_generate_prompt_failure(mock_get_service):
    mock_service = MagicMock()
    mock_service.generate_discussion_prompt = AsyncMock(
        side_effect=Exception("prompt failed")
    )
    mock_get_service.return_value = mock_service

    response = client.post(
        "/intervention/prompt",
        json={"topic": "AI ethics", "context": "kelas 1", "difficulty": "medium"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["prompt"] == ""
    assert data["error"] == "Internal error"


@patch.object(
    __import__("app.api.routes", fromlist=["settings"]).settings,
    "ENABLE_EFFICIENCY_GUARD",
    False,
)
def test_get_high_frequency_queries_disabled():
    response = client.get("/efficiency/high-frequency-queries", params={"limit": 3})

    assert response.status_code == 200
    assert response.json()["enabled"] is False


@patch.object(
    __import__("app.api.routes", fromlist=["settings"]).settings,
    "ENABLE_EFFICIENCY_GUARD",
    True,
)
@patch("app.api.routes.efficiency.get_efficiency_guard")
def test_get_high_frequency_queries_failure(mock_get_guard):
    mock_guard = MagicMock()
    mock_guard.get_high_frequency_queries.side_effect = Exception("hfq failed")
    mock_get_guard.return_value = mock_guard

    response = client.get("/efficiency/high-frequency-queries", params={"limit": 2})

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


@patch("app.api.routes.analytics.get_orchestrator")
def test_get_group_analytics_alias_failure(mock_get_orchestrator):
    mock_orchestrator = MagicMock()
    mock_orchestrator.get_group_dashboard_data = AsyncMock(
        side_effect=Exception("alias failed")
    )
    mock_get_orchestrator.return_value = mock_orchestrator

    response = client.get("/analytics/group/group-1")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["group_id"] == "group-1"
    assert data["error"] == "Internal error"


@patch("app.api.routes.analytics.get_mongo_logger")
def test_analytics_export_json_failure(mock_get_mongo_logger):
    mock_logger = MagicMock()
    mock_logger.export_to_csv = AsyncMock(
        side_effect=Exception("general export failed")
    )
    mock_get_mongo_logger.return_value = mock_logger

    response = client.get("/analytics/export")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["error"] == "Internal error"


@patch("app.api.routes.documents.get_vector_store")
def test_delete_document_failure_with_collection_name(mock_get_vector_store):
    mock_store = MagicMock()
    mock_store.delete_documents = AsyncMock(
        side_effect=Exception("delete with collection failed")
    )
    mock_get_vector_store.return_value = mock_store

    response = client.delete(
        "/documents/doc-2", params={"collection_name": "course_if101"}
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "INTERNAL_SERVER_ERROR"


# --- Legacy provider removal: migrated routes propagate provider_context ---


@patch("app.api.routes.discussion_direction.settings")
@patch("app.api.routes.discussion_direction.get_llm_service")
def test_classify_relevance_forwards_provider_context(mock_get_llm, mock_settings):
    mock_settings.UNIFIED_PROVIDER_ENABLED = True
    mock_settings.UNIFIED_PROVIDER_ORCHESTRATION = True

    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        return_value=MagicMock(
            success=True,
            content='{"classifications":[{"messageId":"m1","isRelevant":true}]}',
        )
    )
    mock_get_llm.return_value = mock_llm

    response = client.post(
        "/classify-relevance",
        json={
            "messages": [{"id": "m1", "content": "test"}],
            "goal": "learn AI",
            "provider_context": {
                "version": "1.0",
                "provider": {"name": "openai", "displayName": "OpenAI"},
                "execution": {"baseUrl": "https://api.example/v1", "model": "gpt-4"},
                "auth": {"type": "api-key", "credential": "sk-test"},
                "metadata": {
                    "featureFamily": "orchestration",
                    "requestId": "r1",
                    "resolvedAt": "2026-01-01T00:00:00Z",
                },
            },
        },
    )

    assert response.status_code == 200
    call_kwargs = mock_get_llm.call_args
    assert call_kwargs[1].get("provider_context") is not None


@patch("app.api.routes.discussion_direction.settings")
@patch("app.api.routes.discussion_direction.get_llm_service")
def test_session_summary_forwards_provider_context(mock_get_llm, mock_settings):
    mock_settings.UNIFIED_PROVIDER_ENABLED = True
    mock_settings.UNIFIED_PROVIDER_ORCHESTRATION = True

    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        return_value=MagicMock(
            success=True,
            content='{"goalAchieved":true,"topics":["AI"],"contributions":{"Peserta":1},"assessment":"Bagus"}',
        )
    )
    mock_get_llm.return_value = mock_llm

    response = client.post(
        "/session-summary",
        json={
            "messages": [{"content": "hello", "senderName": "Alice"}],
            "goal": "learn AI",
            "provider_context": {
                "version": "1.0",
                "provider": {"name": "openai", "displayName": "OpenAI"},
                "execution": {"baseUrl": "https://api.example/v1", "model": "gpt-4"},
                "auth": {"type": "api-key", "credential": "sk-test"},
                "metadata": {
                    "featureFamily": "orchestration",
                    "requestId": "r1",
                    "resolvedAt": "2026-01-01T00:00:00Z",
                },
            },
        },
    )

    assert response.status_code == 200
    call_kwargs = mock_get_llm.call_args
    assert call_kwargs[1].get("provider_context") is not None


@patch("app.api.routes.interventions.settings")
@patch("app.api.routes.interventions.get_intervention_service")
def test_intervention_prompt_forwards_provider_context(mock_get_service, mock_settings):
    mock_settings.UNIFIED_PROVIDER_ENABLED = True
    mock_settings.UNIFIED_PROVIDER_INTERVENTIONS = True

    mock_service = MagicMock()
    mock_service.generate_discussion_prompt = AsyncMock(
        return_value=MagicMock(success=True, message="Discuss X", error=None)
    )
    mock_get_service.return_value = mock_service

    response = client.post(
        "/intervention/prompt",
        json={
            "topic": "AI ethics",
            "provider_context": {
                "version": "1.0",
                "provider": {"name": "openai", "displayName": "OpenAI"},
                "execution": {"baseUrl": "https://api.example/v1", "model": "gpt-4"},
                "auth": {"type": "api-key", "credential": "sk-test"},
                "metadata": {
                    "featureFamily": "interventions",
                    "requestId": "r1",
                    "resolvedAt": "2026-01-01T00:00:00Z",
                },
            },
        },
    )

    assert response.status_code == 200
    call_kwargs = mock_get_service.call_args
    assert call_kwargs[1].get("provider_context") is not None


@patch("app.api.routes.goals.settings")
@patch("app.api.routes.goals.get_orchestrator")
def test_goal_refine_forwards_provider_context(mock_get_orchestrator, mock_settings):
    mock_settings.UNIFIED_PROVIDER_ENABLED = True
    mock_settings.UNIFIED_PROVIDER_GOALS = True

    mock_orch = MagicMock()
    mock_orch.get_goal_refinement = AsyncMock(
        return_value={"success": True, "refined_goal": "improved goal"}
    )
    mock_get_orchestrator.return_value = mock_orch

    import json

    provider_ctx = json.dumps(
        {
            "version": "1.0",
            "provider": {"name": "openai", "displayName": "OpenAI"},
            "execution": {"baseUrl": "https://api.example/v1", "model": "gpt-4"},
            "auth": {"type": "api-key", "credential": "sk-test"},
            "metadata": {
                "featureFamily": "goals",
                "requestId": "r1",
                "resolvedAt": "2026-01-01T00:00:00Z",
            },
        }
    )

    response = client.post(
        "/goals/refine",
        data={
            "current_goal": "learn programming",
            "missing_criteria": '["measurable"]',
            "provider_context": provider_ctx,
        },
    )

    assert response.status_code == 200
    call_kwargs = mock_get_orchestrator.call_args
    assert call_kwargs[1].get("provider_context") is not None
