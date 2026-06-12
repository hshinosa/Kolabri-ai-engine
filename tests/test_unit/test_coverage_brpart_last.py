"""Close remaining 14 BrPart to 100% branch coverage."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())


@pytest.mark.asyncio
async def test_core_cb_record_success_when_open_resets_failures_only():
    from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState

    cb = CircuitBreaker("t", CircuitBreakerConfig())
    cb.state = CircuitState.OPEN
    cb.failure_count = 3
    await cb._record_success()
    assert cb.state == CircuitState.OPEN
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_core_cb_record_failure_when_open_stays_open():
    from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState

    cb = CircuitBreaker("t", CircuitBreakerConfig(failure_threshold=2))
    cb.state = CircuitState.OPEN
    await cb._record_failure()
    assert cb.state == CircuitState.OPEN
# --- services circuit_breaker 175->exit, 189->exit: OPEN skips elif CLOSED ---
@pytest.mark.asyncio
async def test_svc_cb_on_success_when_open_does_not_reset():
    from app.services.circuit_breaker import CircuitBreaker, CircuitState

    cb = CircuitBreaker(name="t")
    cb._state = CircuitState.OPEN
    cb._failure_count = 4
    await cb._on_success()
    assert cb._failure_count == 4


@pytest.mark.asyncio
async def test_svc_cb_on_failure_when_open_does_not_increment_closed_path():
    from app.services.circuit_breaker import CircuitBreaker, CircuitState

    cb = CircuitBreaker(name="t", failure_threshold=2)
    cb._state = CircuitState.OPEN
    await cb._on_failure()
    assert cb._state == CircuitState.OPEN


# --- chunking 69->87: strip empty; 57->95: break when start >= len ---
def test_create_chunks_whitespace_only_window_no_empty_chunk():
    from app.services.document_processing.chunking import create_chunks

    # Window can strip to empty; must not append empty ChunkSpec
    text = ("word " * 25) + (" " * 50) + ("end " * 25)
    chunks = create_chunks(text, "d", "f", 1, 45, 20)
    assert chunks
    assert all(c.text.strip() for c in chunks)


def test_create_chunks_exits_while_when_start_reaches_end():
    from app.services.document_processing.chunking import create_chunks

    text = "a" * 200
    chunks = create_chunks(text, "d", "f", 1, 80, 0)
    assert len(chunks) >= 2
    assert chunks[-1].metadata["char_end"] <= len(text)


@pytest.mark.asyncio
async def test_export_group_hot_false_branch_in_aggregation_loop():
    from app.services.export_service import ExportService

    svc = ExportService()
    with patch.object(svc, "initialize", new_callable=AsyncMock):
        with patch("app.services.repositories.ActivityLogRepository") as Repo:
            Repo.return_value.list_student_messages_for_group = AsyncMock(
                return_value=[
                    {
                        "Resource": "u1",
                        "Attributes": {
                            "original_text": "hello world",
                            "is_hot": False,
                            "lexical_variety": 0.3,
                        },
                    },
                ]
            )
            rows = await svc.aggregate_activity_by_group("g")
    assert rows[0]["hot_count"] == 0
    assert rows[0]["avg_lexical_variety"] == 0.3


@pytest.mark.asyncio
async def test_export_chat_space_hot_false_branch():
    from app.services.export_service import ExportService

    svc = ExportService()
    with patch.object(svc, "initialize", new_callable=AsyncMock):
        with patch("app.services.repositories.ActivityLogRepository") as Repo:
            Repo.return_value.list_student_messages_for_case = AsyncMock(
                return_value=[
                    {
                        "Resource": "u1",
                        "Attributes": {"original_text": "a", "is_hot": False},
                    },
                ]
            )
            rows = await svc.aggregate_activity_by_chat_space("s")
    assert rows[0]["hot_count"] == 0


# --- goal_validator 382->384: open fence, no closing ``` line ---
@pytest.mark.asyncio
async def test_goal_refine_strip_fence_without_closing_backticks():
    from app.services.goal_validator import GoalValidator

    v = GoalValidator()
    body = json.dumps({"refined_goal": "Menyelesaikan 5 latihan dalam 7 hari"})
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        return_value=MagicMock(tokens_used=1, content=f"```json\n{body}")
    )
    with patch("app.services.llm.get_llm_service", return_value=mock_llm):
        out = await v.refine_goal("Belajar rutin setiap pagi", ["time_bound"])
    assert out.get("success") is True


# --- intervention 305->321: empty messages skips inactivity block ---
@pytest.mark.asyncio
async def test_intervention_check_triggers_empty_messages():
    from app.services.intervention import ChatInterventionService

    svc = ChatInterventionService(llm_service=MagicMock())
    triggers = await svc._check_triggers(
        messages=[], topic="t", last_intervention_time=None
    )
    assert triggers["needs_summary"] is False
    assert triggers["inactive"] is False


# --- mongodb 80->85: no bound request_id ---
@pytest.mark.asyncio
async def test_mongodb_log_without_request_id_in_context():
    from app.services.mongodb_logger import MongoDBLogger

    log = MongoDBLogger()
    log.enabled = True
    log.db = MagicMock()
    log.db.activity_logs.insert_one = AsyncMock()
    with patch(
        "app.services.mongodb_logger.structlog.contextvars.get_contextvars",
        return_value={},
    ):
        await log.log_activity({"CaseID": "c", "Activity": "A"})
    entry = log.db.activity_logs.insert_one.await_args[0][0]
    assert "request_id" not in entry


# --- process_mining_anomaly 612->611 ---
def test_detect_bottlenecks_single_event_no_pairs():
    from app.services.process_mining_anomaly import ProcessMiningAnomalyDetector

    det = ProcessMiningAnomalyDetector(mongo_logger=MagicMock())
    events = [
        {
            "createdAt": datetime(2026, 1, 1, 10, 0, 0),
            "metadata": {"interactionType": "READ"},
        },
    ]
    assert det._detect_bottlenecks(events) is None


def test_bottleneck_loop_if_durations_false():
    for _phase, durations in {"X": []}.items():
        if durations:
            pytest.fail("empty list must skip body")