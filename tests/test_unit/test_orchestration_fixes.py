"""Regression tests for orchestration fixes.

- S1: state reads in _generate_intervention_message / handle_message must
  acquire _state_lock (these tests fail without the lock wrap).
- B5: DB/anomaly/alignment failures are logged via logger.exception instead
  of vanishing through bare ``except: pass``.
"""

import asyncio
from datetime import datetime

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.orchestration import Orchestrator
from app.services.nlp_analytics import EngagementAnalysis, EngagementType


def make_analysis():
    return EngagementAnalysis(
        lexical_variety=0.5,
        engagement_type=EngagementType.COGNITIVE,
        is_higher_order=True,
        hot_indicators=[],
        word_count=10,
        unique_words=8,
        confidence=0.8,
    )


@pytest.fixture
def patched_settings():
    with patch("app.services.orchestration.settings") as mock_settings:
        mock_settings.INTERVENTION_MIN_MESSAGES = 5
        mock_settings.INTERVENTION_COOLDOWN_MINUTES = 5
        mock_settings.NLP_LOW_LEXICAL_THRESHOLD = 0.3
        mock_settings.NLP_QUALITY_ALERT_THRESHOLD = 40
        mock_settings.LOGIC_LISTENER_PARTICIPATION_INEQUITY_THRESHOLD = 0.5
        yield mock_settings


@pytest.fixture
def orchestrator_factory(patched_settings):
    def _make():
        mock_rag = AsyncMock()
        mock_rag.query = AsyncMock(
            return_value=MagicMock(
                answer="test",
                success=True,
                sources=[],
                scaffolding_triggered=False,
                grounding_ratio=None,
                srl_phase=None,
                srl_sub_phase=None,
            )
        )

        mock_analyzer = MagicMock()
        mock_analyzer.analyze_interaction = MagicMock(return_value=make_analysis())
        mock_analyzer.extract_srl_object = MagicMock(return_value="Topic")
        mock_analyzer.get_discussion_quality_score = MagicMock(
            return_value={"quality_score": 75, "recommendation": "Good"}
        )

        mock_mongo = AsyncMock()
        mock_mongo.log_activity = AsyncMock()
        mock_mongo.log_intervention = AsyncMock()
        mock_mongo.get_activity_logs = AsyncMock(return_value=[])
        mock_mongo.db = MagicMock()

        mock_intervention = MagicMock()
        mock_intervention.analyze_and_intervene = AsyncMock(
            return_value=MagicMock(message="Intervene!", should_intervene=True)
        )

        mock_logic = MagicMock()
        mock_logic.track_participation = AsyncMock()
        mock_logic.update_last_message_time = AsyncMock()
        mock_logic.get_group_status = MagicMock(
            return_value={"participation_gini": 0.3}
        )

        mock_goal = MagicMock()
        mock_goal.validate_goal = MagicMock(
            return_value=MagicMock(
                is_valid=True, score=0.9, feedback="Valid goal", missing_criteria=[]
            )
        )

        mock_notification = MagicMock()
        mock_notification.notify_teacher = AsyncMock()

        mock_anomaly = MagicMock()
        mock_anomaly.detect_session_anomalies = AsyncMock(
            return_value=MagicMock(
                has_anomalies=False,
                description="",
                anomaly_type="",
                severity="low",
                timestamp=datetime(2024, 1, 1, 8, 0, 0),
            )
        )

        mock_plan = MagicMock()
        mock_plan.analyze_session = AsyncMock(
            return_value=MagicMock(
                comparison={"alignment_score": 82},
                insights=["Keep focus"],
            )
        )

        with (
            patch(
                "app.services.orchestration.get_mongo_logger",
                return_value=mock_mongo,
            ),
            patch(
                "app.services.orchestration.get_plan_vs_reality_analyzer",
                return_value=mock_plan,
            ),
            patch(
                "app.services.orchestration.get_anomaly_detector",
                return_value=mock_anomaly,
            ),
            patch(
                "app.services.orchestration.get_notification_service",
                return_value=mock_notification,
            ),
        ):
            orchestrator = Orchestrator(
                rag=mock_rag,
                analyzer=mock_analyzer,
                intervention=mock_intervention,
                pm_logger=MagicMock(),
                goal_validator=mock_goal,
                logic_listener=mock_logic,
            )

        orchestrator.mongo_logger = mock_mongo
        orchestrator.anomaly_detector = mock_anomaly
        orchestrator.notification_service = mock_notification
        orchestrator.plan_vs_reality = mock_plan

        mocks = {
            "rag": mock_rag,
            "analyzer": mock_analyzer,
            "intervention": mock_intervention,
            "logic": mock_logic,
            "mongo": mock_mongo,
            "anomaly": mock_anomaly,
            "plan": mock_plan,
            "notification": mock_notification,
        }
        return orchestrator, mocks

    return _make


# --- S1: lock consistency ---


@pytest.mark.asyncio
async def test_generate_intervention_message_reads_state_under_lock(
    orchestrator_factory,
):
    """State reads must wait on _state_lock (fails if reads are unlocked)."""
    orchestrator, mocks = orchestrator_factory()
    orchestrator._group_messages["g1"] = [
        {"user_id": "u1", "message": "halo", "timestamp": datetime.now()}
    ]
    orchestrator._last_intervention["g1"] = datetime(2024, 1, 1, 8, 0, 0)

    async with orchestrator._state_lock:
        task = asyncio.create_task(
            orchestrator._generate_intervention_message(
                "g1", make_analysis(), 30, "low_quality", "Topik", {}
            )
        )
        await asyncio.sleep(0.05)
        assert not task.done(), "read ran while _state_lock was held"
        assert mocks["intervention"].analyze_and_intervene.await_count == 0

    result = await task
    assert result == "Intervene!"
    call = mocks["intervention"].analyze_and_intervene.await_args
    assert call.kwargs["messages"] == [
        {"role": "user", "content": "halo", "sender_id": "u1"}
    ]
    assert call.kwargs["last_intervention_time"] == datetime(2024, 1, 1, 8, 0, 0)

# --- B5: swallowed DB/anomaly failures must be logged ---


@pytest.mark.asyncio
async def test_alignment_failure_is_logged(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()
    orchestrator._group_messages["g1"] = [
        {
            "user_id": "u1",
            "message": "halo",
            "timestamp": datetime.now(),
            "is_hot": True,
            "lexical_variety": 0.5,
        }
    ]
    orchestrator.plan_vs_reality.analyze_session = AsyncMock(
        side_effect=RuntimeError("pm db down")
    )

    with (
        patch.object(
            orchestrator,
            "_get_latest_session_id",
            new=AsyncMock(return_value="3"),
        ),
        patch("app.services.orchestration.logger") as mock_logger,
    ):
        result = await orchestrator.get_group_analytics("g1")

    assert result["alignment"] == {}
    mock_logger.exception.assert_called_once_with("alignment_analysis_failed")


@pytest.mark.asyncio
async def test_session_id_lookup_failure_is_logged(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()

    with (
        patch(
            "app.services.repositories.ActivityLogRepository",
            side_effect=RuntimeError("db down"),
        ),
        patch("app.services.orchestration.logger") as mock_logger,
    ):
        result = await orchestrator._get_latest_session_id("g1")

    assert result == "1"
    mock_logger.exception.assert_called_once_with("session_id_lookup_failed")


@pytest.mark.asyncio
async def test_intervention_impact_failure_is_logged(orchestrator_factory):
    orchestrator, _ = orchestrator_factory()

    with (
        patch(
            "app.services.repositories.ActivityLogRepository",
            side_effect=RuntimeError("db down"),
        ),
        patch("app.services.orchestration.logger") as mock_logger,
    ):
        result = await orchestrator._calculate_intervention_impact("g1")

    assert result == {"status": "unknown"}
    mock_logger.exception.assert_called_once_with(
        "intervention_impact_calculation_failed"
    )


@pytest.mark.asyncio
async def test_dashboard_anomaly_detector_failure_is_logged(orchestrator_factory):
    orchestrator, mocks = orchestrator_factory()
    mocks["anomaly"].detect_session_anomalies = AsyncMock(
        side_effect=RuntimeError("detector down")
    )

    analytics = {
        "quality_score": 72,
        "participation_equity": 0.3,
        "hot_percentage": 60.0,
        "lexical_variety": 0.5,
        "quality_breakdown": {"lexical_variety": 0.5},
        "message_count": 4,
        "participants": ["u1"],
        "engagement_distribution": {"u1": 4},
    }

    with (
        patch.object(
            orchestrator,
            "_get_latest_session_id",
            new=AsyncMock(return_value="5"),
        ),
        patch.object(
            orchestrator,
            "get_group_analytics",
            new=AsyncMock(return_value=analytics),
        ),
        patch.object(
            orchestrator,
            "_calculate_intervention_impact",
            new=AsyncMock(return_value={"status": "none"}),
        ),
        patch("app.services.orchestration.logger") as mock_logger,
    ):
        result = await orchestrator.get_group_dashboard_data("g11")

    assert result["anomalies"] == []
    mock_logger.exception.assert_called_once_with("dashboard_anomaly_check_failed")
