"""Branch coverage for app/api/routes gaps (analytics, chat, discussion_direction, health)."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("redis.asyncio", MagicMock())
sys.modules.setdefault("redis", MagicMock())
sys.modules.setdefault("prometheus_client", MagicMock())

from app.api.routes import router as api_router


def _health_client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router)
    return TestClient(app)


def _analytics_client() -> TestClient:
    from app.api.routes.analytics import router as analytics_router

    app = FastAPI()
    app.include_router(analytics_router)
    return TestClient(app)


def _chat_client() -> TestClient:
    from app.api.routes.chat import router as chat_router

    app = FastAPI()
    app.include_router(chat_router)
    return TestClient(app)


def _discussion_client() -> TestClient:
    from app.api.routes.discussion_direction import router as dd_router

    app = FastAPI()
    app.include_router(dd_router)
    return TestClient(app)


async def _stream_with_empty_choices():
    yield SimpleNamespace(choices=[])


async def _stream_with_content_delta():
    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Hi"))])


# --- analytics.py: 280→288 (total_events>0), 284→282 (empty parts skip) ---


@patch("app.api.routes.analytics.get_mongo_logger")
def test_analytics_export_json_skips_data_rows_with_empty_parts(mock_get_mongo):
    """Cover loop at 282-285 when split yields no parts (284→282)."""
    mock_logger = MagicMock()
    mock_logger.export_to_csv = AsyncMock(
        return_value="CaseID,Activity\n,OnlyComma\n1,Start\n"
    )
    mock_get_mongo.return_value = mock_logger

    resp = _analytics_client().get("/analytics/export")

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["total_events"] == 2
    assert data["unique_cases"] == 1


@patch("app.api.routes.analytics.get_mongo_logger")
def test_analytics_export_json_zero_events_skips_case_loop(mock_get_mongo):
    """Cover total_events==0 branch (280→288 false)."""
    mock_logger = MagicMock()
    mock_logger.export_to_csv = AsyncMock(return_value="CaseID,Activity\n")
    mock_get_mongo.return_value = mock_logger

    resp = _analytics_client().get("/analytics/export")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_events"] == 0
    assert data["unique_cases"] == 0


# --- chat.py: 273→271 (delta without content skips yield) ---


@patch("app.api.routes.chat.get_llm_service")
def test_personal_chat_stream_skips_chunks_without_text_delta(mock_get_llm):
    mock_llm = MagicMock()
    mock_llm.model = "gpt-test"
    mock_llm.client.chat.completions.create = AsyncMock(
        return_value=_stream_with_empty_choices()
    )
    mock_get_llm.return_value = mock_llm

    resp = _chat_client().post(
        "/chat/personal/stream",
        json={"message": "hello", "history": []},
    )

    assert resp.status_code == 200
    assert 'data: {"content":' not in resp.text
    assert "data: [DONE]" in resp.text


@patch("app.api.routes.chat.get_llm_service")
def test_personal_chat_stream_yields_content_delta(mock_get_llm):
    mock_llm = MagicMock()
    mock_llm.model = "gpt-test"
    mock_llm.client.chat.completions.create = AsyncMock(
        return_value=_stream_with_content_delta()
    )
    mock_get_llm.return_value = mock_llm

    resp = _chat_client().post(
        "/chat/personal/stream",
        json={"message": "hello", "history": []},
    )

    assert resp.status_code == 200
    assert '"content": "Hi"' in resp.text
    assert "data: [DONE]" in resp.text


# --- discussion_direction.py: 110→122, 112→122 ---


def test_classify_relevance_empty_messages_via_http():
    resp = _discussion_client().post(
        "/classify-relevance",
        json={"messages": [], "goal": "Tujuan pembelajaran"},
    )
    assert resp.status_code == 200
    assert resp.json()["classifications"] == []


@patch("app.api.routes.discussion_direction.get_llm_service")
def test_classify_relevance_llm_failure_pads_defaults(mock_get_llm):
    llm = MagicMock()
    llm.generate = AsyncMock(return_value=SimpleNamespace(success=False, content=None))
    mock_get_llm.return_value = llm

    resp = _discussion_client().post(
        "/classify-relevance",
        json={
            "messages": [{"id": "m1", "content": "diskusi"}],
            "goal": "Tujuan",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["classifications"] == [
        {"messageId": "m1", "isRelevant": True}
    ]


@patch("app.api.routes.discussion_direction.get_llm_service")
def test_classify_relevance_parsed_list_not_classifications_pads(mock_get_llm):
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value=SimpleNamespace(
            success=True, content='{"other": []}'
        )
    )
    mock_get_llm.return_value = llm

    resp = _discussion_client().post(
        "/classify-relevance",
        json={
            "messages": [{"id": "a", "content": "x"}],
            "goal": "Tujuan",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["classifications"] == [
        {"messageId": "a", "isRelevant": True}
    ]


@patch("app.api.routes.discussion_direction.get_llm_service")
def test_classify_relevance_skips_malformed_classification_items(mock_get_llm):
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value=SimpleNamespace(
            success=True,
            content=(
                '{"classifications":['
                '{"messageId":"ok","isRelevant":false},'
                '"bad",'
                '{"noId":true}'
                "]}"
            ),
        )
    )
    mock_get_llm.return_value = llm

    resp = _discussion_client().post(
        "/classify-relevance",
        json={
            "messages": [
                {"id": "ok", "content": "a"},
                {"id": "missing", "content": "b"},
            ],
            "goal": "Tujuan",
        },
    )

    assert resp.status_code == 200
    body = resp.json()["classifications"]
    assert body == [
        {"messageId": "ok", "isRelevant": False},
        {"messageId": "missing", "isRelevant": True},
    ]


# --- health.py: 67→72 (redis ping false while mongo healthy) ---


@patch("app.api.routes.health.get_reranker")
@patch("app.api.routes.health.get_vector_store")
def test_health_mongo_healthy_redis_ping_false(mock_vs, mock_reranker):
    mock_vs_instance = MagicMock()
    mock_vs_instance._ensure_collection = AsyncMock()
    mock_vs.return_value = mock_vs_instance
    mock_reranker.return_value = MagicMock(is_available=MagicMock(return_value=True))

    with (
        patch("app.services.llm.get_llm_service") as mock_llm,
        patch("app.services.mongodb_logger.get_mongo_logger") as mock_mongo,
        patch("app.core.redis_cache.get_redis_cache", new_callable=AsyncMock) as mock_redis,
        patch("app.services.circuit_breaker.get_llm_circuit_breaker") as mock_cb,
    ):
        mock_llm.return_value = MagicMock(model="m")
        mongo = MagicMock()
        mongo.enabled = True
        mongo.ping = AsyncMock(return_value=True)
        mock_mongo.return_value = mongo

        redis = MagicMock()
        redis.ping = AsyncMock(return_value=False)
        mock_redis.return_value = redis

        mock_cb.return_value = MagicMock(state=SimpleNamespace(value="closed"))

        resp = _health_client().get("/health")

    assert resp.status_code == 503
    data = resp.json()
    assert data["dependencies"]["mongo"] == "healthy"
    assert data["dependencies"]["redis"] == "down"


@patch("app.api.routes.health.get_reranker")
@patch("app.api.routes.health.get_vector_store")
def test_health_mongo_disabled_marks_healthy_without_ping(mock_vs, mock_reranker):
    mock_vs_instance = MagicMock()
    mock_vs_instance._ensure_collection = AsyncMock()
    mock_vs.return_value = mock_vs_instance
    mock_reranker.return_value = MagicMock(is_available=MagicMock(return_value=True))

    with (
        patch("app.services.llm.get_llm_service") as mock_llm,
        patch("app.services.mongodb_logger.get_mongo_logger") as mock_mongo,
        patch("app.core.redis_cache.get_redis_cache", new_callable=AsyncMock) as mock_redis,
        patch("app.services.circuit_breaker.get_llm_circuit_breaker") as mock_cb,
    ):
        mock_llm.return_value = MagicMock(model="m")
        mongo = MagicMock()
        mongo.enabled = False
        mongo.ping = AsyncMock()
        mock_mongo.return_value = mongo

        redis = MagicMock()
        redis.ping = AsyncMock(return_value=True)
        mock_redis.return_value = redis

        mock_cb.return_value = MagicMock(state=SimpleNamespace(value="closed"))

        resp = _health_client().get("/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["dependencies"]["mongo"] == "healthy"
    mongo.ping.assert_not_awaited()