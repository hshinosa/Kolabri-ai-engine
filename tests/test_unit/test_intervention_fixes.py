"""Regression tests for timestamp handling in ``_check_triggers``.

Bug B1: the summary-trigger branch ran ``datetime.fromisoformat(
m["timestamp"].replace(...))`` unconditionally, so any ``datetime`` object as a
message timestamp (as ``orchestration._track_message`` stores) raised TypeError
whenever ``last_intervention_time`` was set — i.e. after the first intervention.
The inactivity branch already guarded with ``isinstance(..., str)``.

Contract under test:
- str or datetime timestamps are accepted everywhere a timestamp is compared
- every timestamp is normalized to naive local time, so aware/naive mixes
  (e.g. ISO ``Z`` strings vs ``datetime.now()``) cannot raise
- missing/malformed timestamps are skipped, never KeyError
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.services.intervention import ChatInterventionService


@pytest.fixture
def service():
    return ChatInterventionService(llm_service=MagicMock())


def _datetimes(start: datetime, count: int):
    """Message dicts whose timestamps are datetime objects (orchestration style)."""
    return [
        {
            "sender": f"user_{i % 3}",
            "content": f"Pesan diskusi {i}",
            "timestamp": start + i * timedelta(minutes=1),
        }
        for i in range(count)
    ]


class TestSummaryBranchTimestamps:
    """Summary trigger: cutoff comparison must accept datetime objects (bug B1)."""

    @pytest.mark.asyncio
    async def test_datetime_object_timestamps_do_not_raise(self, service):
        """Regression: datetime timestamps + last_intervention_time used to TypeError."""
        base = datetime(2024, 1, 1, 10, 0, 0)
        messages = _datetimes(base, 12)

        triggers = await service._check_triggers(
            messages=messages,
            topic="Topik diskusi",
            last_intervention_time=base - timedelta(minutes=5),
        )

        assert triggers["needs_summary"] is True

    @pytest.mark.asyncio
    async def test_datetime_timestamps_filtered_against_cutoff(self, service):
        """Messages older than the cutoff are excluded, not just parsed."""
        base = datetime(2024, 1, 1, 10, 0, 0)
        messages = _datetimes(base, 12)

        # Only the 3 messages at minute 9..11 are newer than the cutoff
        triggers = await service._check_triggers(
            messages=messages,
            topic="Topik diskusi",
            last_intervention_time=base + timedelta(minutes=8),
        )

        assert triggers["needs_summary"] is False

    @pytest.mark.asyncio
    async def test_iso_string_timestamps_still_work(self, service):
        base = datetime(2024, 1, 1, 10, 0, 0)
        messages = [
            {**m, "timestamp": m["timestamp"].isoformat()}
            for m in _datetimes(base, 12)
        ]

        triggers = await service._check_triggers(
            messages=messages,
            topic="Topik diskusi",
            last_intervention_time=base - timedelta(minutes=5),
        )

        assert triggers["needs_summary"] is True

    @pytest.mark.asyncio
    async def test_aware_messages_vs_naive_cutoff(self, service):
        """Aware (UTC) message timestamps compared with a naive local cutoff."""
        messages = [
            {"content": f"Pesan {i}", "timestamp": datetime.now(timezone.utc)}
            for i in range(12)
        ]

        triggers = await service._check_triggers(
            messages=messages,
            topic="Topik diskusi",
            last_intervention_time=datetime.now() - timedelta(minutes=5),
        )

        assert triggers["needs_summary"] is True

    @pytest.mark.asyncio
    async def test_naive_messages_vs_aware_cutoff(self, service):
        """Naive local message timestamps compared with an aware cutoff."""
        messages = [
            {"content": f"Pesan {i}", "timestamp": datetime.now()}
            for i in range(12)
        ]

        triggers = await service._check_triggers(
            messages=messages,
            topic="Topik diskusi",
            last_intervention_time=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        # Cutoff is in the future: no message counts as "since intervention"
        assert triggers["needs_summary"] is False

    @pytest.mark.asyncio
    async def test_missing_and_malformed_timestamps_are_skipped(self, service):
        """No KeyError on missing key; unparseable strings are ignored."""
        base = datetime(2024, 1, 1, 10, 0, 0)
        messages = _datetimes(base, 11)
        messages[0] = {"sender": "user_0", "content": "tanpa timestamp"}
        messages.append(
            {"sender": "user_1", "content": "timestamp rusak", "timestamp": "???"}
        )

        triggers = await service._check_triggers(
            messages=messages,
            topic="Topik diskusi",
            last_intervention_time=base - timedelta(minutes=5),
        )

        # 10 valid datetime messages remain, equal to the summary minimum (10)
        assert triggers["needs_summary"] is True


class TestInactivityBranchTimestamps:
    """Inactivity trigger: same normalization, datetime and aware inputs."""

    @pytest.mark.asyncio
    async def test_datetime_object_timestamp_detects_inactivity(self, service):
        messages = [
            {"content": "Halo", "timestamp": datetime.now() - timedelta(minutes=45)}
        ]

        triggers = await service._check_triggers(
            messages=messages, topic="topik", last_intervention_time=None
        )

        assert triggers["inactive"] is True
        assert triggers["should_intervene"] is True

    @pytest.mark.asyncio
    async def test_aware_datetime_object_timestamp_detects_inactivity(self, service):
        messages = [
            {
                "content": "Halo",
                "timestamp": datetime.now(timezone.utc) - timedelta(minutes=45),
            }
        ]

        triggers = await service._check_triggers(
            messages=messages, topic="topik", last_intervention_time=None
        )

        assert triggers["inactive"] is True

    @pytest.mark.asyncio
    async def test_recent_datetime_object_timestamp_not_inactive(self, service):
        messages = [
            {"content": "Halo", "timestamp": datetime.now() - timedelta(minutes=2)}
        ]

        triggers = await service._check_triggers(
            messages=messages, topic="topik", last_intervention_time=None
        )

        assert triggers["inactive"] is False

    @pytest.mark.asyncio
    async def test_missing_or_malformed_timestamp_not_inactive(self, service):
        triggers = await service._check_triggers(
            messages=[{"content": "Halo"}],
            topic="topik",
            last_intervention_time=None,
        )
        assert triggers["inactive"] is False

        triggers = await service._check_triggers(
            messages=[{"content": "Halo", "timestamp": "not-a-date"}],
            topic="topik",
            last_intervention_time=None,
        )
        assert triggers["inactive"] is False
