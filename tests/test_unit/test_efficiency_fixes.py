"""Regression tests: rate-limit reporting must be read-only (bug B4).

`get_rate_limit_info` used to call `check_rate_limit`, which consumes a quota
slot via `RateLimiter.is_allowed` — querying the info endpoint could self-block
the identifier it reports on.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

from app.services.efficiency_guard import EfficiencyGuard, RateLimiter


def test_get_rate_limit_info_does_not_consume_quota():
    guard = EfficiencyGuard(rate_limit_max_requests=3, rate_limit_window_seconds=60)

    first = guard.get_rate_limit_info("user1")
    assert first["remaining_requests"] == 3
    assert first["is_allowed"] is True

    # Reporting N times must not move remaining_requests or block anything.
    for _ in range(10):
        info = guard.get_rate_limit_info("user1")
        assert info["remaining_requests"] == 3
        assert info["is_allowed"] is True

    assert guard.rate_limit_blocks == 0


def test_real_enforcement_still_allows_up_to_max_after_reporting():
    guard = EfficiencyGuard(rate_limit_max_requests=3, rate_limit_window_seconds=60)

    for _ in range(5):
        guard.get_rate_limit_info("user1")

    # Enforcement path unaffected: exactly max_requests allowed, then blocked.
    assert guard.check_rate_limit("user1") is True
    assert guard.check_rate_limit("user1") is True
    assert guard.check_rate_limit("user1") is True
    assert guard.check_rate_limit("user1") is False
    assert guard.rate_limit_blocks == 1

    # Info endpoint now correctly reports exhausted state without consuming more.
    exhausted = guard.get_rate_limit_info("user1")
    assert exhausted["remaining_requests"] == 0
    assert exhausted["is_allowed"] is False
    assert guard.rate_limit_blocks == 1


def test_peek_does_not_append_request_timestamp():
    limiter = RateLimiter(max_requests=5, time_window_seconds=60)

    assert limiter.peek("u1") is True
    assert limiter.peek("u1") is True
    assert len(limiter.requests["u1"]) == 0
    assert limiter.get_remaining_requests("u1") == 5


def test_peek_prunes_expired_window_without_consuming():
    limiter = RateLimiter(max_requests=2, time_window_seconds=60)
    assert limiter.is_allowed("u1") is True
    assert limiter.is_allowed("u1") is True
    assert limiter.peek("u1") is False  # at limit, read-only

    # After the window expires, peek must prune (same as is_allowed) and report
    # allowed without having appended anything.
    with patch("app.services.efficiency_guard.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime.now() + timedelta(seconds=120)
        assert limiter.peek("u1") is True
        assert len(limiter.requests["u1"]) == 0
