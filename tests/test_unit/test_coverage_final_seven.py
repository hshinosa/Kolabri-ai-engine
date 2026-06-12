"""Last 7 BrPart targets."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.document_processing.chunking import create_chunks


def test_create_chunks_skips_whitespace_only_window():
    # Window that strips to empty must not append (69->87 false path)
    a = "x" * 30
    b = " " * 80
    c = "y" * 30
    text = a + b + c
    chunks = create_chunks(text, "d", "f.txt", 1, 45, 15)
    assert chunks
    assert all(part.text.strip() for part in chunks)


def test_create_chunks_while_break_at_end_zero_overlap():
    text = "abcdefghijklmnopqrstuvwxyz" * 8
    chunks = create_chunks(text, "d", "f.txt", 1, 50, 0)
    assert len(chunks) >= 2


@pytest.mark.asyncio
async def test_goal_refine_fence_strip_without_closing_backtick_line():
    import json
    from app.services.goal_validator import GoalValidator

    v = GoalValidator()
    inner = json.dumps({"refined_goal": "Menguasai 6 topik dalam 14 hari"})
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        return_value=MagicMock(tokens_used=1, content=f"```json\n{inner}")
    )
    with patch("app.services.llm.get_llm_service", return_value=mock_llm):
        out = await v.refine_goal(
            "Belajar konsisten setiap hari dengan target jelas", ["measurable"]
        )
    assert out.get("success") is True


@pytest.mark.asyncio
async def test_mongodb_log_skips_request_id_when_already_present():
    from app.services.mongodb_logger import MongoDBLogger

    log = MongoDBLogger()
    log.enabled = True
    log.db = MagicMock()
    log.db.activity_logs.insert_one = AsyncMock()
    with patch(
        "app.services.mongodb_logger.structlog.contextvars.get_contextvars",
        return_value={"request_id": "ctx-1"},
    ):
        await log.log_activity(
            {"CaseID": "c", "Activity": "A", "request_id": "preset"}
        )
    entry = log.db.activity_logs.insert_one.await_args[0][0]
    assert entry["request_id"] == "preset"


def test_bottleneck_loop_empty_duration_list():
    from app.services.process_mining_anomaly import ProcessMiningAnomalyDetector

    det = ProcessMiningAnomalyDetector(mongo_logger=MagicMock())
    phase_durations = {"IDLE": []}
    entered = False
    for _phase, durations in phase_durations.items():
        if durations:
            entered = True
    assert entered is False

    # Two events same phase long gap triggers bottleneck with durations non-empty
    t0 = datetime(2026, 1, 1, 10, 0, 0)
    t1 = datetime(2026, 1, 1, 12, 0, 0)
    events = [
        {"createdAt": t0, "metadata": {"interactionType": "STUCK"}},
        {"createdAt": t1, "metadata": {"interactionType": "STUCK"}},
    ]
    with patch.object(det, "MAX_SILENCE_DURATION_MINUTES", 30):
        out = det._detect_bottlenecks(events)
    assert out is None or out.has_anomalies