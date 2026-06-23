"""Branch coverage for export finalize helpers (cnt == 0)."""

from app.services.export_service import (
    _finalize_session_discussion_metrics,
    _finalize_group_engagement_metrics,
)


def test_finalize_group_skips_zero_message_count():
    metrics = {
        "u1": {
            "message_count": 0,
            "total_lexical_variety": 5.0,
            "hot_count": 0,
            "engagement_score": 0.0,
        },
        "u2": {
            "message_count": 2,
            "total_lexical_variety": 0.6,
            "hot_count": 1,
            "engagement_score": 0.0,
        },
    }
    _finalize_group_engagement_metrics(metrics)
    assert "avg_lexical_variety" not in metrics["u1"]
    assert metrics["u2"]["avg_lexical_variety"] == 0.3
    assert metrics["u2"]["engagement_score"] > 0


def test_finalize_session_discussion_skips_zero_message_count():
    metrics = {
        "u1": {
            "message_count": 0,
            "total_lexical_variety": 1.0,
            "avg_lexical_variety": 0.0,
        },
        "u2": {"message_count": 1, "total_lexical_variety": 0.5, "avg_lexical_variety": 0.0},
    }
    _finalize_session_discussion_metrics(metrics)
    assert metrics["u1"]["avg_lexical_variety"] == 0.0
    assert metrics["u2"]["avg_lexical_variety"] == 0.5