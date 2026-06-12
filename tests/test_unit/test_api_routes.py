import sys
from unittest.mock import MagicMock, AsyncMock, patch
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

from app.api.routes import router
from app.api import dependencies

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_api_dependencies_reexport_functions():
    assert dependencies.get_vector_store is not None
    assert dependencies.get_document_processor is not None
    assert dependencies.get_rag_pipeline is not None
    assert dependencies.get_mongo_logger is not None
    assert dependencies.get_logic_listener is not None
    assert dependencies.get_llm_service is not None
    assert dependencies.get_intervention_service is not None
    assert dependencies.get_orchestrator is not None


@patch("app.api.routes.health.get_reranker")
@patch("app.api.routes.health.get_vector_store")
def test_health_check_healthy(mock_vs, mock_reranker):
    mock_vs_instance = MagicMock()
    mock_vs_instance._ensure_collection = AsyncMock()
    mock_vs.return_value = mock_vs_instance

    mock_reranker_instance = MagicMock()
    mock_reranker_instance.is_available.return_value = True
    mock_reranker.return_value = mock_reranker_instance

    with (
        patch("app.services.llm.get_llm_service") as mock_llm,
        patch("app.services.mongodb_logger.get_mongo_logger") as mock_mongo,
        patch("app.core.redis_cache.get_redis_cache") as mock_redis,
        patch("app.services.circuit_breaker.get_llm_circuit_breaker") as mock_cb,
    ):
        mock_llm_instance = MagicMock()
        mock_llm_instance.model = "test-model"
        mock_llm.return_value = mock_llm_instance

        mock_mongo_instance = MagicMock()
        mock_mongo_instance.enabled = False
        mock_mongo.return_value = mock_mongo_instance

        mock_redis_instance = MagicMock()
        mock_redis_instance.ping = AsyncMock(return_value=True)
        mock_redis.return_value = mock_redis_instance

        mock_cb_instance = MagicMock()
        mock_cb_instance.state.value = "closed"
        mock_cb.return_value = mock_cb_instance

        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@patch("app.api.routes.health.get_reranker")
@patch("app.api.routes.health.get_vector_store")
def test_health_check_degraded(mock_vs, mock_reranker):
    mock_vs_instance = MagicMock()
    mock_vs_instance._ensure_collection = AsyncMock(side_effect=Exception("Failed"))
    mock_vs.return_value = mock_vs_instance

    mock_reranker_instance = MagicMock()
    mock_reranker_instance.is_available.return_value = False
    mock_reranker.return_value = mock_reranker_instance

    with (
        patch("app.services.llm.get_llm_service") as mock_llm,
        patch("app.services.mongodb_logger.get_mongo_logger") as mock_mongo,
        patch("app.core.redis_cache.get_redis_cache") as mock_redis,
        patch("app.services.circuit_breaker.get_llm_circuit_breaker") as mock_cb,
    ):
        mock_llm_instance = MagicMock()
        mock_llm_instance.model = None
        mock_llm.return_value = mock_llm_instance

        mock_mongo_instance = MagicMock()
        mock_mongo_instance.enabled = False
        mock_mongo.return_value = mock_mongo_instance

        mock_redis_instance = MagicMock()
        mock_redis_instance.ping = AsyncMock(return_value=True)
        mock_redis.return_value = mock_redis_instance

        mock_cb_instance = MagicMock()
        mock_cb_instance.state.value = "closed"
        mock_cb.return_value = mock_cb_instance

        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


@patch("app.api.routes.health.get_reranker")
@patch("app.api.routes.health.get_vector_store")
def test_health_check_vector_store_failure(mock_vs, mock_reranker):
    mock_vs_instance = MagicMock()
    mock_vs_instance._ensure_collection = AsyncMock(side_effect=Exception("Failed"))
    mock_vs.return_value = mock_vs_instance

    mock_reranker_instance = MagicMock()
    mock_reranker_instance.is_available.return_value = True
    mock_reranker.return_value = mock_reranker_instance

    with (
        patch("app.services.llm.get_llm_service") as mock_llm,
        patch("app.services.mongodb_logger.get_mongo_logger") as mock_mongo,
        patch("app.core.redis_cache.get_redis_cache") as mock_redis,
        patch("app.services.circuit_breaker.get_llm_circuit_breaker") as mock_cb,
    ):
        mock_llm_instance = MagicMock()
        mock_llm_instance.model = "test-model"
        mock_llm.return_value = mock_llm_instance

        mock_mongo_instance = MagicMock()
        mock_mongo_instance.enabled = False
        mock_mongo.return_value = mock_mongo_instance

        mock_redis_instance = MagicMock()
        mock_redis_instance.ping = AsyncMock(return_value=True)
        mock_redis.return_value = mock_redis_instance

        mock_cb_instance = MagicMock()
        mock_cb_instance.state.value = "closed"
        mock_cb.return_value = mock_cb_instance

        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


@patch("app.api.routes.health.get_reranker")
@patch("app.api.routes.health.get_vector_store")
def test_health_check_mongo_and_breaker_failures(mock_vs, mock_reranker):
    mock_vs_instance = MagicMock()
    mock_vs_instance._ensure_collection = AsyncMock()
    mock_vs.return_value = mock_vs_instance

    mock_reranker_instance = MagicMock()
    mock_reranker_instance.is_available.return_value = True
    mock_reranker.return_value = mock_reranker_instance

    with (
        patch("app.services.llm.get_llm_service") as mock_llm,
        patch(
            "app.services.mongodb_logger.get_mongo_logger",
            side_effect=Exception("mongo down"),
        ),
        patch("app.core.redis_cache.get_redis_cache") as mock_redis,
        patch(
            "app.services.circuit_breaker.get_llm_circuit_breaker",
            side_effect=Exception("breaker down"),
        ),
    ):
        mock_llm_instance = MagicMock()
        mock_llm_instance.model = "test-model"
        mock_llm.return_value = mock_llm_instance

        mock_redis_instance = MagicMock()
        mock_redis_instance.ping = AsyncMock(return_value=True)
        mock_redis.return_value = mock_redis_instance

        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


@patch("app.api.routes.health.get_reranker")
@patch("app.api.routes.health.get_vector_store")
def test_health_check_redis_ping_failure(mock_vs, mock_reranker):
    mock_vs_instance = MagicMock()
    mock_vs_instance._ensure_collection = AsyncMock()
    mock_vs.return_value = mock_vs_instance
    mock_reranker_instance = MagicMock()
    mock_reranker_instance.is_available.return_value = True
    mock_reranker.return_value = mock_reranker_instance

    with (
        patch("app.services.llm.get_llm_service") as mock_llm,
        patch("app.services.mongodb_logger.get_mongo_logger") as mock_mongo,
        patch("app.core.redis_cache.get_redis_cache") as mock_redis_get,
        patch("app.services.circuit_breaker.get_llm_circuit_breaker") as mock_cb,
    ):
        mock_llm.return_value = MagicMock(model="test-model")
        mock_mongo.return_value = MagicMock(enabled=False)
        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock(side_effect=RuntimeError("redis down"))
        mock_redis_get.return_value = mock_redis
        mock_cb.return_value = MagicMock(state=MagicMock(value="closed"))

        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["dependencies"]["redis"] == "down"


@patch("app.api.routes.health.get_reranker")
@patch("app.api.routes.health.get_vector_store")
def test_health_check_redis_get_cache_failure(mock_vs, mock_reranker):
    mock_vs_instance = MagicMock()
    mock_vs_instance._ensure_collection = AsyncMock()
    mock_vs.return_value = mock_vs_instance
    mock_reranker_instance = MagicMock()
    mock_reranker_instance.is_available.return_value = True
    mock_reranker.return_value = mock_reranker_instance

    with (
        patch("app.services.llm.get_llm_service") as mock_llm,
        patch("app.services.mongodb_logger.get_mongo_logger") as mock_mongo,
        patch(
            "app.core.redis_cache.get_redis_cache",
            side_effect=RuntimeError("redis client init failed"),
        ),
        patch("app.services.circuit_breaker.get_llm_circuit_breaker") as mock_cb,
    ):
        mock_llm.return_value = MagicMock(model="test-model")
        mock_mongo.return_value = MagicMock(enabled=False)
        mock_cb.return_value = MagicMock(state=MagicMock(value="closed"))

        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["dependencies"]["redis"] == "down"


def test_track_activity_without_user_id():
    mock_listener = MagicMock()
    mock_listener.update_last_message_time = AsyncMock()
    mock_listener.track_participation = AsyncMock()

    with patch(
        "app.api.routes.track_activity.get_logic_listener", return_value=mock_listener
    ):
        response = client.post("/track-activity", json={"group_id": "g1"})

    assert response.status_code == 200
    assert response.json()["success"] is True
    mock_listener.update_last_message_time.assert_awaited_once_with("g1")
    mock_listener.track_participation.assert_not_awaited()


@patch("app.api.routes.chat.get_rag_pipeline")
def test_ask_question_success(mock_rag):
    mock_pipeline = MagicMock()
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.answer = "This is a test answer"
    mock_result.sources = [{"source": "test.pdf", "page": 1}]
    mock_pipeline.query = AsyncMock(return_value=mock_result)
    mock_rag.return_value = mock_pipeline

    payload = {"query": "test query", "course_id": "test_course"}

    response = client.post("/ask", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "This is a test answer" in data["answer"]
    assert "test.pdf" in data["answer"]


@patch("app.api.routes.chat.get_rag_pipeline")
def test_ask_question_failure(mock_rag):
    mock_pipeline = MagicMock()
    mock_result = MagicMock()
    mock_result.success = False
    mock_result.error = "Test Error"
    mock_pipeline.query = AsyncMock(return_value=mock_result)
    mock_rag.return_value = mock_pipeline

    payload = {"query": "test query", "course_id": "test_course"}

    response = client.post("/ask", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "Maaf, saya tidak bisa menemukan jawaban" in data["answer"]


@patch("app.api.routes.analytics.get_engagement_analyzer")
def test_analyze_engagement(mock_analyzer):
    mock_analyzer_instance = MagicMock()
    mock_analysis = MagicMock()
    mock_analysis.lexical_variety = 0.8
    mock_analysis.engagement_type.value = "cognitive"
    mock_analysis.is_higher_order = True
    mock_analysis.hot_indicators = ["analyze"]
    mock_analyzer_instance.analyze_interaction.return_value = mock_analysis
    mock_analyzer.return_value = mock_analyzer_instance

    payload = {"text": "This is a test where we analyze things."}
    response = client.post("/analytics/engagement", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["lexical_variety"] == 0.8
    assert data["engagement_type"] == "cognitive"


@patch("app.api.routes.analytics.get_redis_cache")
@patch("app.api.routes.analytics.get_orchestrator")
def test_get_group_dashboard(mock_orchestrator, mock_redis):
    mock_orch_instance = MagicMock()
    mock_orch_instance.get_group_dashboard_data = AsyncMock(
        return_value={"group": "data"}
    )
    mock_orchestrator.return_value = mock_orch_instance
    mock_redis_instance = MagicMock()
    mock_redis_instance.generate_key = MagicMock(return_value="k")
    mock_redis_instance.get = AsyncMock(return_value=None)
    mock_redis_instance.set = AsyncMock()
    mock_redis.return_value = mock_redis_instance

    response = client.get("/analytics/dashboard/group/test-group")
    assert response.status_code == 200
    assert response.json() == {"group": "data"}


@patch("app.api.routes.analytics.get_redis_cache")
@patch("app.api.routes.analytics.get_orchestrator")
def test_get_individual_dashboard(mock_orchestrator, mock_redis):
    mock_orch_instance = MagicMock()
    mock_orch_instance.get_individual_dashboard_data = AsyncMock(
        return_value={"individual": "data"}
    )
    mock_orchestrator.return_value = mock_orch_instance
    mock_redis_instance = MagicMock()
    mock_redis_instance.generate_key = MagicMock(return_value="k")
    mock_redis_instance.get = AsyncMock(return_value=None)
    mock_redis_instance.set = AsyncMock()
    mock_redis.return_value = mock_redis_instance

    response = client.get("/analytics/dashboard/individual/test-user")
    assert response.status_code == 200
    assert response.json() == {"individual": "data"}
