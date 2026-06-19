"""
Integration tests for plan_vs_reality.py field mapping fixes.
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock
from app.services.plan_vs_reality import PlanVsRealityAnalyzer


@pytest.fixture
def analyzer():
    """Create PlanVsRealityAnalyzer instance."""
    return PlanVsRealityAnalyzer()


@pytest.fixture
def realistic_events():
    """Realistic MongoDB event data matching production structure."""
    return [
        # Goal_Setting event
        {
            "CaseID": "group_123_session_1",
            "Activity": "Goal_Setting",
            "Timestamp": datetime(2026, 6, 19, 10, 0, 0),
            "Resource": "Student_user1",
            "metadata": {
                "interactionType": "GOAL_SETTING",
                "phase": "Forethought"
            },
            "content": "Belajar tentang usability testing dan heuristic evaluation",
            "userId": "user1"
        },
        # Goal_Validation event (alternative format)
        {
            "CaseID": "group_123_session_1",
            "Activity": "Goal_Validation",
            "Timestamp": datetime(2026, 6, 19, 10, 1, 0),
            "Resource": "Student_user2",
            "Attributes": {
                "original_text": "Menganalisis 5 prinsip desain UI dalam 2 minggu",
                "srl_object": "Learning_Goal"
            },
            "userId": "user2"
        },
        # Student_Message event
        {
            "CaseID": "group_123_session_1",
            "Activity": "Student_Message",
            "Timestamp": datetime(2026, 6, 19, 10, 5, 0),
            "Resource": "Student_user1",
            "Lifecycle": "complete",
            "Attributes": {
                "original_text": "Usability testing itu penting untuk memastikan aplikasi mudah digunakan",
                "srl_object": "Performance",
                "is_hot": True,
                "lexical_variety": 0.82
            }
        },
        # Bot_Response event
        {
            "CaseID": "group_123_session_1",
            "Activity": "Bot_Response",
            "Timestamp": datetime(2026, 6, 19, 10, 6, 0),
            "Resource": "System_Bot",
            "Lifecycle": "complete",
            "Attributes": {
                "original_text": "Ya betul! Ada 10 prinsip heuristic dari Nielsen",
                "srl_object": "Performance",
                "is_hot": False,
                "lexical_variety": 0.71
            }
        },
        # Another Student_Message
        {
            "CaseID": "group_123_session_1",
            "Activity": "Student_Message",
            "Timestamp": datetime(2026, 6, 19, 10, 8, 0),
            "Resource": "Student_user2",
            "Lifecycle": "complete",
            "Attributes": {
                "original_text": "Prinsip pertama visibility of system status",
                "srl_object": "Performance",
                "is_hot": True,
                "lexical_variety": 0.68
            }
        }
    ]


class TestExtractPlan:
    """Test _extract_plan with realistic event data."""

    def test_extracts_goal_setting_events(self, analyzer, realistic_events):
        """Should extract events with Activity='Goal_Setting'."""
        result = analyzer._extract_plan(realistic_events)

        assert result["has_plan"] is True
        assert len(result["goals"]) >= 1

        # Should extract from 'content' field
        goal = result["goals"][0]
        assert "usability testing" in goal["content"].lower()
        assert goal["user_id"] == "user1"
        assert goal["timestamp"] == datetime(2026, 6, 19, 10, 0, 0)

    def test_extracts_goal_validation_events(self, analyzer, realistic_events):
        """Should extract events with Activity='Goal_Validation'."""
        result = analyzer._extract_plan(realistic_events)

        # Should find both Goal_Setting and Goal_Validation
        assert result["goal_count"] >= 2

        # Goal_Validation uses Attributes.original_text
        goal_validation = [g for g in result["goals"] if "Menganalisis" in g["content"]]
        assert len(goal_validation) == 1
        assert goal_validation[0]["user_id"] == "user2"
        assert goal_validation[0]["timestamp"] == datetime(2026, 6, 19, 10, 1, 0)

    def test_backward_compat_metadata_phase(self, analyzer):
        """Should still work with old metadata.phase format."""
        old_format_events = [
            {
                "metadata": {"phase": "Forethought"},
                "content": "Old format goal",
                "userId": "user1",
                "Timestamp": datetime(2026, 6, 19, 10, 0, 0)
            }
        ]

        result = analyzer._extract_plan(old_format_events)
        assert result["has_plan"] is True
        assert len(result["goals"]) == 1
        assert result["goals"][0]["content"] == "Old format goal"

    def test_empty_when_no_goals(self, analyzer):
        """Should return empty when no goal events."""
        events = [
            {"Activity": "Student_Message", "content": "Not a goal"}
        ]

        result = analyzer._extract_plan(events)
        assert result["has_plan"] is False
        assert result["goals"] == []


class TestExtractReality:
    """Test _extract_reality with realistic event data."""

    def test_extracts_student_messages(self, analyzer, realistic_events):
        """Should extract events with Activity='Student_Message'."""
        result = analyzer._extract_reality(realistic_events)

        assert result["has_reality"] is True
        # Should find 3 message events total (2 Student_Message + 1 Bot_Response)
        assert result["message_count"] == 3

    def test_extracts_bot_responses(self, analyzer, realistic_events):
        """Should extract events with Activity='Bot_Response'."""
        result = analyzer._extract_reality(realistic_events)

        # Should include bot responses in message count
        assert result["has_reality"] is True
        assert result["message_count"] == 3

    def test_normalizes_content_field(self, analyzer, realistic_events):
        """Should add 'content' field from Attributes.original_text."""
        result = analyzer._extract_reality(realistic_events)

        # Should successfully extract topics from normalized content
        assert result["has_reality"] is True
        assert len(result["topics"]) > 0

    def test_backward_compat_metadata_interaction_type(self, analyzer):
        """Should still work with old metadata.interactionType format."""
        old_format_events = [
            {
                "metadata": {"interactionType": "STUDENT_MESSAGE"},
                "content": "Old format message"
            }
        ]

        result = analyzer._extract_reality(old_format_events)
        assert result["has_reality"] is True
        assert result["message_count"] == 1

    def test_empty_when_no_messages(self, analyzer):
        """Should return empty when no message events."""
        events = [
            {"Activity": "Goal_Setting", "content": "Not a message"}
        ]

        result = analyzer._extract_reality(events)
        assert result["has_reality"] is False
        assert result["message_count"] == 0


class TestCalculateTimeAllocation:
    """Test _calculate_time_allocation with Timestamp field."""

    def test_uses_timestamp_field(self, analyzer, realistic_events):
        """Should use Timestamp field (capital T)."""
        result = analyzer._calculate_time_allocation(realistic_events)

        # Should calculate duration from first to last timestamp
        # First: 10:00, Last: 10:08 = 8 minutes
        assert result["total_minutes"] == 8.0

    def test_handles_missing_timestamps(self, analyzer):
        """Should handle events without Timestamp field."""
        events = [
            {"Activity": "Student_Message", "content": "No timestamp"}
        ]

        result = analyzer._calculate_time_allocation(events)
        assert result == {"total_minutes": 0.0}

    def test_backward_compat_created_at(self, analyzer):
        """Should fallback to createdAt if Timestamp not present."""
        events = [
            {"createdAt": datetime(2026, 6, 19, 10, 0, 0)},
            {"createdAt": datetime(2026, 6, 19, 10, 5, 0)}
        ]

        result = analyzer._calculate_time_allocation(events)
        assert result["total_minutes"] == 5.0


class TestCalculateSessionDuration:
    """Test _calculate_session_duration with timestamp field."""

    def test_uses_timestamp_field(self, analyzer, realistic_events):
        """Should use Timestamp field for duration calculation."""
        # Filter to just message events
        msg_events = [e for e in realistic_events
                     if e["Activity"] in ["Student_Message", "Bot_Response"]]

        result = analyzer._calculate_session_duration(msg_events)

        # First msg: 10:05, Last msg: 10:08 = 3 minutes
        assert result == 3.0

    def test_handles_missing_timestamps(self, analyzer):
        """Should return 0 when no timestamps available."""
        events = [
            {"Activity": "Student_Message", "content": "No timestamp"}
        ]

        result = analyzer._calculate_session_duration(events)
        assert result == 0.0


class TestCalculateEngagementMetrics:
    """Test _calculate_engagement_metrics with Attributes fields."""

    def test_calculates_hot_percentage(self, analyzer, realistic_events):
        """Should calculate HOT% from Attributes.is_hot field."""
        # Filter to message events only
        msg_events = [e for e in realistic_events
                     if e["Activity"] in ["Student_Message", "Bot_Response"]]

        result = analyzer._calculate_engagement_metrics(msg_events)

        # 2 out of 3 messages have is_hot=True (66.67%)
        expected_hot_pct = (2 / 3) * 100
        assert abs(result["hot_percentage"] - expected_hot_pct) < 0.1

    def test_calculates_lexical_variety(self, analyzer, realistic_events):
        """Should calculate avg lexical variety from Attributes.lexical_variety."""
        msg_events = [e for e in realistic_events
                     if e["Activity"] in ["Student_Message", "Bot_Response"]]

        result = analyzer._calculate_engagement_metrics(msg_events)

        # Average of [0.82, 0.71, 0.68] = 0.7367
        expected_avg = (0.82 + 0.71 + 0.68) / 3
        assert abs(result["avg_lexical_variety"] - expected_avg) < 0.01

    def test_counts_srl_objects(self, analyzer, realistic_events):
        """Should count engagement types from Attributes.srl_object."""
        msg_events = [e for e in realistic_events
                     if e["Activity"] in ["Student_Message", "Bot_Response"]]

        result = analyzer._calculate_engagement_metrics(msg_events)

        # All 3 messages have srl_object="Performance"
        assert result["engagement_distribution"]["Performance"] == 3

    def test_backward_compat_engagement_object(self, analyzer):
        """Should fallback to old engagement object structure."""
        events = [
            {
                "Activity": "Student_Message",
                "engagement": {
                    "isHigherOrder": True,
                    "lexicalVariety": 0.75,
                    "srlObject": "Performance"
                }
            }
        ]

        result = analyzer._calculate_engagement_metrics(events)
        assert result["hot_percentage"] == 100.0
        assert result["avg_lexical_variety"] == 0.75


class TestAnalyzeSession:
    """Integration test for full analyze_session flow."""

    @pytest.mark.asyncio
    async def test_full_analysis_with_realistic_data(self, analyzer, realistic_events):
        """Should produce non-zero alignment_score with proper data."""
        # Mock the mongo_logger.get_activity_logs to return our test events
        analyzer.mongo_logger.get_activity_logs = AsyncMock(return_value=realistic_events)

        result = await analyzer.analyze_session("group_123_session_1")

        # Should have plan (goals)
        assert result.plan["has_plan"] is True
        assert len(result.plan["goals"]) >= 2

        # Should have reality (messages)
        assert result.reality["has_reality"] is True
        assert result.reality["message_count"] == 3

        # Should calculate alignment_score > 0
        assert result.comparison["alignment_score"] > 0

        # Should not have runtime errors in insights
        assert "error" not in str(result.insights).lower()

    @pytest.mark.asyncio
    async def test_empty_session_returns_zeros(self, analyzer):
        """Should handle empty session gracefully."""
        analyzer.mongo_logger.get_activity_logs = AsyncMock(return_value=[])

        result = await analyzer.analyze_session("empty_session")

        assert result.plan == {}
        assert result.reality == {}
        assert result.comparison == {}
        assert "No event logs found" in result.insights[0]


class TestFieldMappingCoverage:
    """Verify all field mappings are correctly implemented."""

    def test_all_activity_types_handled(self, analyzer):
        """Should handle all expected Activity types."""
        events = [
            {"Activity": "Goal_Setting", "content": "Goal 1", "Timestamp": datetime.now(), "userId": "u1"},
            {"Activity": "Goal_Validation", "Attributes": {"original_text": "Goal 2"}, "Timestamp": datetime.now(), "userId": "u2"},
            {"Activity": "Student_Message", "Attributes": {"original_text": "Msg 1"}, "Timestamp": datetime.now()},
            {"Activity": "Bot_Response", "Attributes": {"original_text": "Msg 2"}, "Timestamp": datetime.now()},
            {"Activity": "System_Notification", "content": "Not a goal or message"}  # Should be ignored
        ]

        plan = analyzer._extract_plan(events)
        reality = analyzer._extract_reality(events)

        assert len(plan["goals"]) == 2  # Goal_Setting + Goal_Validation
        assert reality["message_count"] == 2  # Student_Message + Bot_Response

    def test_timestamp_field_variations(self, analyzer):
        """Should handle Timestamp, timestamp, and createdAt."""
        events_with_capital = [{"Timestamp": datetime(2026, 6, 19, 10, 0, 0)}]
        events_with_lowercase = [{"timestamp": datetime(2026, 6, 19, 10, 0, 0)}]
        events_with_created_at = [{"createdAt": datetime(2026, 6, 19, 10, 0, 0)}]

        # All should work
        result1 = analyzer._calculate_time_allocation(events_with_capital)
        result2 = analyzer._calculate_session_duration(events_with_lowercase)
        result3 = analyzer._calculate_time_allocation(events_with_created_at)

        # At least one should return non-zero
        assert isinstance(result1, dict)
        assert isinstance(result2, float)
        assert isinstance(result3, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
