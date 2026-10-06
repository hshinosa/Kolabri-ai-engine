"""Test endpoint klasifikasi SRL ringan (POST /api/srl/classify)."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.api.routes.srl import SrlClassifyRequest, classify_srl


def _run(message: str):
    req = SrlClassifyRequest(
        message=message,
        group_id="g-e2e",
        chat_room_id="s-e2e",
        user_id="u-1",
        topic=None,
    )
    with patch("app.api.routes.srl.get_mongo_logger") as ml:
        ml.return_value.log_activity = AsyncMock()
        result = asyncio.run(classify_srl(req))
        logged_calls = ml.return_value.log_activity.await_count
    return result, logged_calls


def test_signal_message_classified_and_logged():
    result, calls = _run(
        "Sebelum kita mulai, topik kita hari ini adalah analisis sorting. "
        "Rencananya kita bagi tugas dan target kita selesai Jumat."
    )
    assert result.success is True
    assert result.phase == "forethought"
    assert result.logged is True
    assert result.confidence > 0.3
    assert calls == 1


def test_no_signal_message_not_logged():
    result, calls = _run("123")
    assert result.success is True
    assert result.logged is False
    assert result.phase == "performance"
    assert result.confidence == 0.3
    assert calls == 0


def test_reflection_signal_classified():
    result, calls = _run(
        "Kesimpulannya kita sudah paham materi ini. Ternyata pilihan metode "
        "tergantung data. Lain kali kita evaluasi diri dulu."
    )
    assert result.phase == "reflection"
    assert result.logged is True
    assert calls == 1


def test_case_id_format_matches_analytics_aggregation():
    """CaseID harus `<groupId>_session_<sessionDiscussionId>` seperti jalur @ai."""
    req = SrlClassifyRequest(
        message="target kita jelas, rencananya kita mulai",
        group_id="g1",
        chat_room_id="s9",
        user_id="u1",
    )
    with patch("app.api.routes.srl.get_mongo_logger") as ml:
        mock = AsyncMock()
        ml.return_value.log_activity = mock
        asyncio.run(classify_srl(req))
        entry = mock.await_args.args[0]
    assert entry["CaseID"] == "g1_session_s9"
    assert entry["Activity"] == "Student_Message"
    assert entry["Attributes"]["srl_phase"] in {
        "forethought",
        "performance",
        "reflection",
    }
