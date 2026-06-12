"""One targeted test per remaining BrPart (coverage-remaining-gaps.md)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())


# analytics 284->282 — baris data kosong (total_events tetap 0 → loop case tidak jalan)
@pytest.mark.asyncio
async def test_analytics_export_only_header_no_data_rows():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.routes.analytics import router as analytics_router

    app = FastAPI()
    app.include_router(analytics_router)
    client = TestClient(app)
    mock_mongo = MagicMock()
    mock_mongo.export_to_csv = AsyncMock(return_value="CaseID,Activity\n")
    with patch("app.api.routes.analytics.get_mongo_logger", return_value=mock_mongo):
        r = client.get("/analytics/export")
    assert r.status_code == 200
    assert r.json()["total_events"] == 0
    assert r.json()["unique_cases"] == 0


# core circuit_breaker 166->exit — CLOSED success resets failures (else branch)
@pytest.mark.asyncio
async def test_core_cb_record_success_half_open_then_closed_resets():
    from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState

    cb = CircuitBreaker("t", CircuitBreakerConfig(failure_threshold=5, success_threshold=1))
    cb.state = CircuitState.HALF_OPEN
    cb.half_open_calls = 0
    await cb._record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 0


# services circuit_breaker 175->exit — CLOSED failure below threshold stays closed
@pytest.mark.asyncio
async def test_svc_cb_failure_closed_does_not_open_below_threshold():
    from app.services.circuit_breaker import CircuitBreaker, CircuitState

    cb = CircuitBreaker(name="t", failure_threshold=5, success_threshold=2)
    cb._state = CircuitState.CLOSED
    cb._failure_count = 2
    await cb._on_failure()
    assert cb._state == CircuitState.CLOSED
    assert cb._failure_count == 3


# services circuit_breaker 189->exit — reset not yet due
def test_svc_cb_should_not_reset_before_timeout():
    from datetime import datetime

    from app.services.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker(name="t", recovery_timeout=300)
    cb._last_failure_time = datetime.now()
    assert cb._should_attempt_reset() is False


# chunking 69->87 — slice hanya whitespace → tidak append chunk
def test_create_chunks_whitespace_slice_skips_empty_chunk_text():
    from app.services.document_processing.chunking import create_chunks

    text = "a" * 50 + "   " * 30 + "b" * 50
    chunks = create_chunks(text, "d", "f.txt", 1, 40, 5)
    assert all(c.text.strip() for c in chunks)


# chunking 57->95 — overlap memaksa start = end
def test_create_chunks_zero_overlap_advance():
    from app.services.document_processing.chunking import create_chunks

    text = "word " * 80
    chunks = create_chunks(text, "d", "f.txt", 1, 100, 0)
    assert len(chunks) >= 2


# export 80->78 — user tanpa pesan (cnt==0) lewati avg
@pytest.mark.asyncio
async def test_export_group_skips_zero_message_count_in_final_loop():
    from app.services.export_service import ExportService

    svc = ExportService()
    with patch.object(svc, "initialize", new_callable=AsyncMock):
        with patch("app.services.repositories.ActivityLogRepository") as Repo:
            Repo.return_value.list_student_messages_for_group = AsyncMock(return_value=[])
            rows = await svc.aggregate_activity_by_group("g1")
    assert rows == []


# export 136->135 — chat space tanpa pesan
@pytest.mark.asyncio
async def test_export_chat_space_skips_zero_message_avg():
    from app.services.export_service import ExportService

    svc = ExportService()
    with patch.object(svc, "initialize", new_callable=AsyncMock):
        with patch("app.services.repositories.ActivityLogRepository") as Repo:
            Repo.return_value.list_student_messages_for_case = AsyncMock(return_value=[])
            rows = await svc.aggregate_activity_by_chat_space("s1")
    assert rows == []


# goal_validator 382->384 — fence buka tanpa baris penutup ```
@pytest.mark.asyncio
async def test_goal_refine_strips_open_fence_without_closing_line():
    from app.services.goal_validator import GoalValidator

    validator = GoalValidator()
    body = json.dumps({"refined_goal": "Menyelesaikan 3 modul dalam 2 minggu"})
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        return_value=MagicMock(tokens_used=1, content=f"```json\n{body}\n")
    )
    with patch("app.services.llm.get_llm_service", return_value=mock_llm):
        out = await validator.refine_goal(
            "Saya ingin belajar struktur data dengan rutin", ["time_bound"]
        )
    assert out.get("success") is True


# intervention 305->321 — cukup pesan tapi sedikit sejak intervensi terakhir
@pytest.mark.asyncio
async def test_intervention_summary_not_set_when_few_messages_since_last():
    from app.services.intervention import ChatInterventionService

    svc = ChatInterventionService(llm_service=MagicMock())
    svc.minimum_messages_for_summary = 5
    now = datetime.now(timezone.utc)
    messages = [
        {"timestamp": (now - timedelta(minutes=i)).isoformat(), "content": f"m{i}"}
        for i in range(6, 0, -1)
    ]
    triggers = await svc._check_triggers(
        messages=messages,
        topic="sql",
        last_intervention_time=now - timedelta(minutes=2),
    )
    assert triggers["needs_summary"] is False


# mongodb 80->85 — enabled tapi insert gagal
@pytest.mark.asyncio
async def test_mongodb_log_activity_insert_exception_path():
    from app.services.mongodb_logger import MongoDBLogger

    log = MongoDBLogger()
    log.enabled = True
    log.db = MagicMock()
    log.db.activity_logs.insert_one = AsyncMock(side_effect=RuntimeError("db down"))
    with patch("app.services.mongodb_logger.logger.error") as err:
        await log.log_activity({"CaseID": "c", "Activity": "A"})
    err.assert_called_once()


# xes_exporter 76->71 — atribut int (float branch)
def test_xes_exporter_int_attribute_uses_float():
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
            "attributes": {"count": 7},
        },
    )
    assert ev.find("float[@key='count']") is not None


# vector_store 199->208 — delete by ids (bukan where)
@pytest.mark.asyncio
async def test_vector_store_delete_by_ids_branch():
    from app.services.vector_store import VectorStoreService

    svc = VectorStoreService()
    svc._initialized = True
    svc._client = MagicMock()
    with patch.object(svc, "_ensure_collection", new_callable=AsyncMock):
        await svc.delete_documents(collection_name="c", ids=["doc-1"])
    svc._client.delete.assert_called_once()


# process_mining_anomaly 612->611 — fase dengan durations kosong
def test_detect_bottlenecks_skips_empty_durations_in_loop():
    from datetime import datetime

    from app.services.process_mining_anomaly import ProcessMiningAnomalyDetector

    det = ProcessMiningAnomalyDetector()
    t0 = datetime(2026, 1, 1, 10, 0, 0)
    events = [
        {"createdAt": t0, "metadata": {"interactionType": "READING"}},
        {"createdAt": t0, "metadata": {"interactionType": "WRITING"}},
    ]
    result = det._detect_bottlenecks(events)
    assert result is None or not result.has_anomalies

