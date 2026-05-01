import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

# Mock heavier modules before imports
sys.modules['chromadb'] = MagicMock()
sys.modules['chromadb.config'] = MagicMock()
sys.modules['chromadb.utils'] = MagicMock()
sys.modules['hnswlib'] = MagicMock()
sys.modules['pypdf'] = MagicMock()
sys.modules['fitz'] = MagicMock()
sys.modules['docx'] = MagicMock()
sys.modules['pptx'] = MagicMock()
sys.modules['openpyxl'] = MagicMock()
sys.modules['pandas'] = MagicMock()
sys.modules['numpy'] = MagicMock()
sys.modules['PIL'] = MagicMock()
sys.modules['motor'] = MagicMock()
sys.modules['motor.motor_asyncio'] = MagicMock()
sys.modules['redis.asyncio'] = MagicMock()
sys.modules['redis'] = MagicMock()
sys.modules['prometheus_client'] = MagicMock()

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.batch_routes import (
    router,
    BatchAskRequest,
    BatchAskResponse,
    _generate_cache_key,
    _process_single_ask,
)


app = FastAPI()
app.include_router(router)
client = TestClient(app)


def _make_request(**overrides):
    data = {
        "query": "Apa itu machine learning?",
        "course_id": "course-1",
        "user_name": "tester",
        "chat_space_id": "space-1",
        "request_id": "req-1",
    }
    data.update(overrides)
    return BatchAskRequest(**data)


def _make_rag_result(success=True, answer="Jawaban", error=None, sources=None):
    return SimpleNamespace(
        success=success,
        answer=answer,
        error=error,
        sources=sources or [],
    )


@patch("app.api.batch_routes.get_llm_service")
@patch("app.api.batch_routes.get_redis_cache")
@patch("app.api.batch_routes.get_rag_pipeline")
def test_batch_ask_with_successful_responses(mock_rag, mock_redis, mock_llm):
    mock_llm.return_value = MagicMock()
    redis_cache = MagicMock()
    redis_cache.get = AsyncMock(return_value=None)
    redis_cache.set = AsyncMock()
    mock_redis.return_value = redis_cache

    rag_pipeline = MagicMock()
    rag_pipeline.query = AsyncMock(
        side_effect=[
            _make_rag_result(
                success=True,
                answer="AI adalah bidang ilmu komputer",
                sources=[{"source": "modul-ai.pdf", "page": 3}],
            ),
            _make_rag_result(success=True, answer="ML adalah subset dari AI", sources=[]),
        ]
    )
    mock_rag.return_value = rag_pipeline

    response = client.post(
        "/ask/batch",
        json={
            "requests": [
                {"query": "Apa itu AI?", "course_id": "c1", "request_id": "r1"},
                {"query": "Apa itu ML?", "course_id": "c1", "request_id": "r2"},
            ],
            "priority": "high",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_requests"] == 2
    assert payload["successful_count"] == 2
    assert payload["failed_count"] == 0
    assert payload["from_cache_count"] == 0
    assert payload["results"][0]["success"] is True
    assert "AI adalah bidang ilmu komputer" in payload["results"][0]["answer"]
    assert "modul-ai.pdf" in payload["results"][0]["answer"]
    assert payload["results"][1]["request_id"] == "r2"
    assert redis_cache.set.await_count == 2


@patch("app.api.batch_routes.get_llm_service")
@patch("app.api.batch_routes.get_redis_cache")
@patch("app.api.batch_routes.get_rag_pipeline")
def test_batch_ask_with_mixed_success_failure(mock_rag, mock_redis, mock_llm):
    mock_llm.return_value = MagicMock()
    redis_cache = MagicMock()
    redis_cache.get = AsyncMock(return_value=None)
    redis_cache.set = AsyncMock()
    mock_redis.return_value = redis_cache

    rag_pipeline = MagicMock()
    rag_pipeline.query = AsyncMock(
        side_effect=[
            _make_rag_result(success=True, answer="Jawaban sukses", sources=[]),
            _make_rag_result(success=False, answer="Jawaban gagal", error="RAG failed", sources=[]),
        ]
    )
    mock_rag.return_value = rag_pipeline

    response = client.post(
        "/ask/batch",
        json={
            "requests": [
                {"query": "Q1", "course_id": "c1", "request_id": "ok"},
                {"query": "Q2", "course_id": "c1", "request_id": "bad"},
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["successful_count"] == 1
    assert payload["failed_count"] == 1
    assert payload["results"][0]["success"] is True
    assert payload["results"][1]["success"] is False
    assert payload["results"][1]["error"] == "RAG failed"
    redis_cache.set.assert_awaited_once()


@patch("app.api.batch_routes.get_llm_service")
@patch("app.api.batch_routes.get_redis_cache")
@patch("app.api.batch_routes.get_rag_pipeline")
def test_batch_ask_with_cache_hit(mock_rag, mock_redis, mock_llm):
    mock_llm.return_value = MagicMock()
    redis_cache = MagicMock()
    redis_cache.get = AsyncMock(return_value={"answer": "cached answer"})
    redis_cache.set = AsyncMock()
    mock_redis.return_value = redis_cache

    rag_pipeline = MagicMock()
    rag_pipeline.query = AsyncMock()
    mock_rag.return_value = rag_pipeline

    response = client.post(
        "/ask/batch",
        json={
            "requests": [
                {"query": "Cached?", "course_id": "c1", "request_id": "cache-1"}
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["successful_count"] == 1
    assert payload["from_cache_count"] == 1
    assert payload["results"][0]["from_cache"] is True
    assert payload["results"][0]["answer"] == "cached answer"
    rag_pipeline.query.assert_not_called()
    redis_cache.set.assert_not_called()


def test_batch_ask_exceeding_max_batch_size():
    requests = [{"query": f"Q{i}", "course_id": "c1", "request_id": str(i)} for i in range(51)]
    response = client.post("/ask/batch", json={"requests": requests})

    assert response.status_code == 422


@patch("app.api.batch_routes.get_llm_service")
@patch("app.api.batch_routes.get_redis_cache")
@patch("app.api.batch_routes.get_rag_pipeline")
def test_batch_ask_with_exception_in_one_request_isolated(mock_rag, mock_redis, mock_llm):
    mock_llm.return_value = MagicMock()
    redis_cache = MagicMock()
    redis_cache.get = AsyncMock(return_value=None)
    redis_cache.set = AsyncMock()
    mock_redis.return_value = redis_cache

    rag_pipeline = MagicMock()
    rag_pipeline.query = AsyncMock(side_effect=[RuntimeError("boom"), _make_rag_result(success=True, answer="still works")])
    mock_rag.return_value = rag_pipeline

    response = client.post(
        "/ask/batch",
        json={
            "requests": [
                {"query": "bad query", "course_id": "c1", "request_id": "bad-1"},
                {"query": "good query", "course_id": "c1", "request_id": "good-1"},
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["successful_count"] == 1
    assert payload["failed_count"] == 1
    assert payload["results"][0]["success"] is False
    assert payload["results"][0]["error"] == "boom"
    assert payload["results"][1]["success"] is True


@patch("app.api.batch_routes.get_llm_service")
@patch("app.api.batch_routes.get_redis_cache")
@patch("app.api.batch_routes.get_rag_pipeline")
def test_precomputed_batch_with_all_cache_hits(mock_rag, mock_redis, mock_llm):
    mock_llm.return_value = MagicMock()
    mock_rag.return_value = MagicMock()
    redis_cache = MagicMock()
    redis_cache.mget = AsyncMock(return_value=[{"answer": "A1"}, {"answer": "A2"}])
    mock_redis.return_value = redis_cache

    response = client.post(
        "/ask/batch/precomputed",
        json={
            "requests": [
                {"query": "Q1", "course_id": "c1", "request_id": "1"},
                {"query": "Q2", "course_id": "c1", "request_id": "2"},
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["successful_count"] == 2
    assert payload["failed_count"] == 0
    assert payload["from_cache_count"] == 2
    assert [r["answer"] for r in payload["results"]] == ["A1", "A2"]


@patch("app.api.batch_routes.get_llm_service")
@patch("app.api.batch_routes.get_redis_cache")
@patch("app.api.batch_routes.get_rag_pipeline")
def test_precomputed_batch_with_all_cache_misses(mock_rag, mock_redis, mock_llm):
    mock_llm.return_value = MagicMock()
    mock_rag.return_value = MagicMock()
    redis_cache = MagicMock()
    redis_cache.mget = AsyncMock(return_value=[None, None])
    mock_redis.return_value = redis_cache

    response = client.post(
        "/ask/batch/precomputed",
        json={
            "requests": [
                {"query": "Q1", "course_id": "c1", "request_id": "1"},
                {"query": "Q2", "course_id": "c1", "request_id": "2"},
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["successful_count"] == 0
    assert payload["failed_count"] == 2
    assert payload["from_cache_count"] == 0
    assert all(result["error"] == "Query not pre-computed" for result in payload["results"])


@patch("app.api.batch_routes.get_llm_service")
@patch("app.api.batch_routes.get_redis_cache")
@patch("app.api.batch_routes.get_rag_pipeline")
def test_precomputed_batch_with_mixed_hits_misses(mock_rag, mock_redis, mock_llm):
    mock_llm.return_value = MagicMock()
    mock_rag.return_value = MagicMock()
    redis_cache = MagicMock()
    redis_cache.mget = AsyncMock(return_value=[{"answer": "cached"}, None])
    mock_redis.return_value = redis_cache

    response = client.post(
        "/ask/batch/precomputed",
        json={
            "requests": [
                {"query": "Q1", "course_id": "c1", "request_id": "1"},
                {"query": "Q2", "course_id": "c1", "request_id": "2"},
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["successful_count"] == 1
    assert payload["failed_count"] == 1
    assert payload["results"][0]["from_cache"] is True
    assert payload["results"][1]["from_cache"] is False
    assert payload["results"][1]["error"] == "Query not pre-computed"


def test_generate_cache_key_deterministic():
    request = _make_request(query="same query", course_id="same-course")

    key_1 = _generate_cache_key(request)
    key_2 = _generate_cache_key(request)
    key_3 = _generate_cache_key(_make_request(query="different query", course_id="same-course"))

    assert key_1 == key_2
    assert key_1.startswith("rag:batch:")
    assert key_1 != key_3


@pytest.mark.asyncio
@patch("app.api.batch_routes.get_redis_cache")
@patch("app.api.batch_routes.get_rag_pipeline")
async def test_process_single_ask_success_path(mock_rag, mock_redis):
    redis_cache = MagicMock()
    redis_cache.get = AsyncMock(return_value=None)
    redis_cache.set = AsyncMock()
    mock_redis.return_value = redis_cache

    rag_pipeline = MagicMock()
    rag_pipeline.query = AsyncMock(
        return_value=_make_rag_result(
            success=True,
            answer="Ringkasan materi",
            sources=[
                {"source": "week1.pdf", "page": 5},
                {"source": "week2.pdf"},
            ],
        )
    )
    mock_rag.return_value = rag_pipeline

    request = _make_request(query="jelaskan materi", course_id="if101", request_id="proc-1")
    result = await _process_single_ask(request)

    assert isinstance(result, BatchAskResponse)
    assert result.success is True
    assert result.from_cache is False
    assert "Ringkasan materi" in result.answer
    assert "week1.pdf (hal. 5)" in result.answer
    assert "week2.pdf" in result.answer
    redis_cache.set.assert_awaited_once()
    _, set_kwargs = redis_cache.set.await_args
    assert set_kwargs["ttl"] == 3600


@pytest.mark.asyncio
@patch("app.api.batch_routes.get_redis_cache")
@patch("app.api.batch_routes.get_rag_pipeline")
async def test_process_single_ask_timeout(mock_rag, mock_redis):
    redis_cache = MagicMock()
    redis_cache.get = AsyncMock(return_value=None)
    redis_cache.set = AsyncMock()
    mock_redis.return_value = redis_cache

    rag_pipeline = MagicMock()
    rag_pipeline.query = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_rag.return_value = rag_pipeline

    request = _make_request(request_id="timeout-1")
    result = await _process_single_ask(request)

    assert result.success is False
    assert result.error == "Request timeout"
    assert result.from_cache is False
    redis_cache.set.assert_not_called()


@pytest.mark.asyncio
@patch("app.api.batch_routes.get_redis_cache")
@patch("app.api.batch_routes.get_rag_pipeline")
async def test_process_single_ask_general_exception(mock_rag, mock_redis):
    redis_cache = MagicMock()
    redis_cache.get = AsyncMock(return_value=None)
    redis_cache.set = AsyncMock()
    mock_redis.return_value = redis_cache

    rag_pipeline = MagicMock()
    rag_pipeline.query = AsyncMock(side_effect=RuntimeError("unexpected failure"))
    mock_rag.return_value = rag_pipeline

    request = _make_request(request_id="err-1")
    result = await _process_single_ask(request)

    assert result.success is False
    assert result.error == "unexpected failure"
    assert result.answer == ""
    assert result.from_cache is False
