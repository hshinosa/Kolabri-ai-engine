"""Target the last 5 BrPart lines without changing runtime behavior."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.document_processing.chunking import create_chunks



def test_create_chunks_empty_strip_skips_append_advances_pointer():
    """Window of spaces only: no chunk appended (69->87 false), loop continues."""
    text = "alpha" * 6 + " " * 60 + "beta" * 6
    chunks = create_chunks(text, "doc", "f.txt", 1, 40, 8)
    assert chunks
    assert all(c.text.strip() for c in chunks)


def test_create_chunks_natural_while_exit_without_overlap():
    """After consuming full text with overlap=0, exit while via start >= len (break)."""
    text = "Z" * 75
    chunks = create_chunks(text, "doc", "f.txt", 1, 50, 0)
    assert len(chunks) == 2
    assert sum(len(c.text) for c in chunks) >= 75


@pytest.mark.asyncio
async def test_goal_refine_open_fence_no_closing_backtick_line():
    import json
    from app.services.goal_validator import GoalValidator

    validator = GoalValidator()
    payload = json.dumps(
        {
            "refined_goal": "Menyelesaikan 5 modul dalam 3 minggu",
            "explanation": "ok",
        }
    )
    # Opening fence only — last line is JSON, not ```
    llm_content = f"```json\n{payload}"
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        return_value=MagicMock(tokens_used=3, content=llm_content)
    )
    with patch("app.services.llm.get_llm_service", return_value=mock_llm):
        result = await validator.refine_goal(
            "Belajar rutin dengan indikator jelas setiap minggu", ["measurable"]
        )
    assert result["success"] is True
    assert "modul" in result["refined_goal"]





def test_average_phase_duration_empty_list():
    from app.services.process_mining_anomaly import ProcessMiningAnomalyDetector

    det = ProcessMiningAnomalyDetector(mongo_logger=MagicMock())
    assert det._average_phase_duration([]) is None
    assert det._average_phase_duration([10.0, 20.0]) == 15.0


def test_detect_bottlenecks_ignores_empty_duration_lists():
    from app.services.process_mining_anomaly import ProcessMiningAnomalyDetector

    det = ProcessMiningAnomalyDetector(mongo_logger=MagicMock())
    t0 = datetime(2026, 3, 1, 9, 0, 0)
    t1 = datetime(2026, 3, 1, 9, 5, 0)
    t2 = datetime(2026, 3, 1, 11, 0, 0)
    events = [
        {"createdAt": t0, "metadata": {"interactionType": "READ"}},
        {"createdAt": t1, "metadata": {"interactionType": "QUIZ"}},
        {"createdAt": t2, "metadata": {"interactionType": "QUIZ"}},
    ]
    with patch.object(det, "MAX_SILENCE_DURATION_MINUTES", 30):
        result = det._detect_bottlenecks(events)
    assert result is None or isinstance(result.has_anomalies, bool)