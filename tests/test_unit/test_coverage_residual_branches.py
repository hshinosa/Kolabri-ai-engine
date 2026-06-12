"""Residual BrPart / stmt gaps after coverage-remaining-gaps.md pass."""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("redis.asyncio", MagicMock())
sys.modules.setdefault("redis", MagicMock())


# analytics 284->282: line that splits to empty parts
@pytest.mark.asyncio
async def test_analytics_export_empty_csv_row_skips_case_id():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.routes.analytics import router as analytics_router

    app = FastAPI()
    app.include_router(analytics_router)
    client = TestClient(app)
    mock_mongo = MagicMock()
    mock_mongo.export_to_csv = AsyncMock(return_value="h\n\n,,\nC1,A\n")
    with patch("app.api.routes.analytics.get_mongo_logger", return_value=mock_mongo):
        r = client.get("/analytics/export")
    assert r.status_code == 200
    assert r.json()["unique_cases"] >= 1


# goal_validator markdown branches
@pytest.mark.asyncio
async def test_goal_refine_open_fence_only_no_close():
    from app.services.goal_validator import GoalValidator

    validator = GoalValidator()
    inner = json.dumps({"refined_goal": "Menguasai 5 topik dalam 1 minggu"})
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        return_value=MagicMock(tokens_used=1, content=f"```json\n{inner}")
    )
    with patch("app.services.llm.get_llm_service", return_value=mock_llm):
        out = await validator.refine_goal(
            "Belajar Python dasar dengan konsisten setiap hari", ["measurable"]
        )
    assert out.get("success") is True


@pytest.mark.asyncio
async def test_goal_refine_non_str_content_before_encode():
    from app.services.goal_validator import GoalValidator

    validator = GoalValidator()
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        return_value=MagicMock(
            tokens_used=1,
            content=123,
        )
    )
    with patch("app.services.llm.get_llm_service", return_value=mock_llm):
        out = await validator.refine_goal("goal", ["specific"])
    assert out.get("success") is False


def test_reranker_reload_with_fastembed_sets_available_true():
    import app.services.reranker as mod

    saved_available = mod.CROSS_ENCODER_AVAILABLE
    fake = MagicMock()
    fake.TextCrossEncoder = MagicMock()
    try:
        with patch.dict(sys.modules, {"fastembed.rerank.cross_encoder": fake}):
            reloaded = importlib.reload(mod)
        assert reloaded.CROSS_ENCODER_AVAILABLE is True
    finally:
        importlib.reload(mod)


# config 234->237 duplicate docs warning
def test_settings_production_docs_enabled_twice_warns():
    with patch("app.core.config.logger.warning") as w:
        from app.core.config import Settings

        Settings(
            ENV="production",
            OPENAI_API_KEY="sk-prod-key-1234567890abcdefghijklmnopqrst",
            OPENAI_BASE_URL="https://api.openai.com/v1",
            CORE_API_URL="https://api.example.com",
            CORE_API_SECRET="strong-production-secret-not-default",
            DEBUG=False,
            DOCS_ENABLED=True,
            ENABLE_DOCS_IN_PRODUCTION=True,
        )
    assert w.call_count >= 2


# core circuit_breaker CLOSED branch in _record_success
@pytest.mark.asyncio
async def test_core_cb_record_success_closed_clears_failures():
    from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState

    cb = CircuitBreaker("x", CircuitBreakerConfig())
    cb.state = CircuitState.CLOSED
    cb.failure_count = 2
    await cb._record_success()
    assert cb.failure_count == 0


# services circuit_breaker
@pytest.mark.asyncio
async def test_svc_cb_on_success_half_open_below_threshold():
    from app.services.circuit_breaker import CircuitBreaker, CircuitState

    cb = CircuitBreaker(name="t", failure_threshold=5, success_threshold=3)
    cb._state = CircuitState.HALF_OPEN
    cb._success_count = 1
    await cb._on_success()
    assert cb._state == CircuitState.HALF_OPEN


@pytest.mark.asyncio
async def test_svc_cb_on_failure_closed_below_threshold():
    from app.services.circuit_breaker import CircuitBreaker, CircuitState

    cb = CircuitBreaker(name="t", failure_threshold=10, success_threshold=2)
    cb._state = CircuitState.CLOSED
    await cb._on_failure()
    assert cb._state == CircuitState.CLOSED
    assert cb._failure_count == 1


# rag_quality 150->153 empty expected
def test_rag_quality_recall_one_when_no_expected_sources():
    from app.services.rag_quality import (
        RetrievalEvaluationCase,
        RetrievalQualityEvaluator,
        RetrievalQualityReviewCriteria,
    )

    ev = RetrievalQualityEvaluator(RetrievalQualityReviewCriteria(min_cases=1))
    summary = ev.evaluate_suite(
        [
            RetrievalEvaluationCase(
                query="q",
                expected_sources=[],
                retrieved_sources=["a"],
            )
        ]
    )
    assert summary.average_source_recall == 1.0


# mongodb 80->85 disabled
@pytest.mark.asyncio
async def test_mongodb_log_activity_when_disabled():
    from app.services.mongodb_logger import MongoDBLogger

    log = MongoDBLogger()
    log.enabled = False
    log.db = MagicMock()
    await log.log_activity({"CaseID": "1", "Activity": "A"})
    log.db.activity_logs.insert_one.assert_not_called()


# vector_store delete where
@pytest.mark.asyncio
async def test_vector_store_delete_by_where():
    from app.services.vector_store import VectorStoreService

    svc = VectorStoreService()
    svc._initialized = True
    svc._client = MagicMock()
    with patch.object(svc, "_ensure_collection", new_callable=AsyncMock):
        await svc.delete_documents(collection_name="c", where={"k": "v"})
    svc._client.delete.assert_called_once()


# xes bool attr
def test_xes_exporter_boolean_attribute():
    import xml.etree.ElementTree as ET

    from app.services.xes_exporter import XESExporter

    exp = XESExporter()
    ev = ET.Element("event")
    exp._add_event_attributes(
        ev,
        {
            "activity": "A",
            "timestamp": datetime.now(),
            "resource": "r",
            "attributes": {"ok": True},
        },
    )
    assert any(child.tag.endswith("boolean") for child in ev)


# chunking long path
def test_create_chunks_multipart_separator():
    from app.services.document_processing.chunking import create_chunks

    body = ("First part. " * 30) + "\n\n" + ("Second part. " * 30)
    chunks = create_chunks(body, "d", "f.txt", 1, 180, 40)
    assert len(chunks) >= 2


@pytest.mark.asyncio
async def test_intervention_summary_skipped_without_last_intervention_time():
    from app.services.intervention import ChatInterventionService

    svc = ChatInterventionService(llm_service=MagicMock())
    svc.minimum_messages_for_summary = 3
    now = datetime.now(timezone.utc)
    messages = [
        {"timestamp": now.isoformat(), "content": "a"},
        {"timestamp": now.isoformat(), "content": "b"},
        {"timestamp": now.isoformat(), "content": "c"},
    ]
    triggers = await svc._check_triggers(
        messages=messages,
        topic="sql",
        last_intervention_time=None,
    )
    assert triggers["needs_summary"] is False


@pytest.mark.asyncio
async def test_analytics_export_row_with_only_commas_no_case_id():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.routes.analytics import router as analytics_router

    app = FastAPI()
    app.include_router(analytics_router)
    client = TestClient(app)
    mock_mongo = MagicMock()
    mock_mongo.export_to_csv = AsyncMock(return_value="CaseID,Act\n,,\n")
    with patch("app.api.routes.analytics.get_mongo_logger", return_value=mock_mongo):
        r = client.get("/analytics/export")
    assert r.status_code == 200
    assert r.json()["unique_cases"] == 0