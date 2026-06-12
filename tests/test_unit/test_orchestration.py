import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from app.services.orchestration import Orchestrator, OrchestrationResult
from app.services.nlp_analytics import EngagementAnalysis, EngagementType


@pytest.fixture
def mock_services():
    return {
        "rag": AsyncMock(),
        "analyzer": MagicMock(),
        "intervention": MagicMock(),
        "pm_logger": MagicMock(),
        "goal_validator": MagicMock(),
        "logic_listener": AsyncMock(),
        "notification_service": AsyncMock(),
    }


@pytest.fixture
def orchestrator(mock_services):
    with (
        patch("app.services.orchestration.get_mongo_logger") as mock_mongo,
        patch("app.services.orchestration.get_plan_vs_reality_analyzer"),
        patch("app.services.orchestration.get_anomaly_detector"),
    ):
        mock_mongo.return_value = MagicMock()
        mock_mongo.return_value.log_activity = AsyncMock()
        mock_mongo.return_value.log_intervention = AsyncMock()
        mock_mongo.return_value.get_activity_logs = AsyncMock(return_value=[])
        return Orchestrator(**mock_services)


@pytest.mark.asyncio
async def test_handle_message_success(orchestrator, mock_services):
    mock_services["analyzer"].analyze_interaction.return_value = EngagementAnalysis(
        lexical_variety=0.8,
        engagement_type=EngagementType.COGNITIVE,
        is_higher_order=True,
        hot_indicators=["menganalisis"],
        word_count=10,
        unique_words=8,
        confidence=1.0,
    )
    mock_services["analyzer"].extract_srl_object.return_value = "TestTopic"
    mock_services["rag"].query.return_value = MagicMock(
        answer="Bot response",
        success=True,
        sources=["source1"],
        scaffolding_triggered=False,
    )

    with patch.object(orchestrator, "_should_intervene", return_value=(False, None)):
        res = await orchestrator.handle_message(
            user_id="user1",
            group_id="group1",
            message="Hello asisten",
            chat_room_id="room_123",
        )

    assert res.success is True
    assert res.reply == "Bot response"


@pytest.mark.asyncio
async def test_validate_goal(orchestrator, mock_services):
    mock_services["goal_validator"].validate_goal.return_value = MagicMock(
        is_valid=True, score=1.0, feedback="Good", missing_criteria=[], details={}
    )
    mock_services["goal_validator"].generate_socratic_hint.return_value = "Hint"

    res = await orchestrator.validate_goal("Target saya lulus", "u1", "group1")
    assert res["is_valid"] is True
    assert res["socratic_hint"] == "Hint"


@pytest.mark.asyncio
async def test_scaffolding_early_applied(orchestrator, mock_services):
    """Test that early scaffolding config results in scaffolding_level=early and outcome=applied."""
    mock_services["rag"].query.return_value = MagicMock(
        answer="Step-by-step explanation",
        success=True,
        sources=["source1"],
        scaffolding_triggered=True,
    )
    with patch.object(orchestrator, "_should_intervene", return_value=(False, None)):
        res = await orchestrator.handle_message(
            user_id="u1",
            group_id="g1",
            message="Explain recursion",
            chat_room_id="room_1",
            scaffolding_config={"scaffolding_level": "early", "enabled": True},
        )
    assert res.success is True
    assert res.analytics["scaffolding_level"] == "early"
    assert res.analytics["scaffolding_outcome"] == "applied"


@pytest.mark.asyncio
async def test_scaffolding_disabled(orchestrator, mock_services):
    """Test that enabled=false results in scaffolding_outcome=disabled."""
    mock_services["rag"].query.return_value = MagicMock(
        answer="Normal answer",
        success=True,
        sources=["source1"],
        scaffolding_triggered=False,
    )
    with patch.object(orchestrator, "_should_intervene", return_value=(False, None)):
        res = await orchestrator.handle_message(
            user_id="u1",
            group_id="g1",
            message="Explain recursion",
            chat_room_id="room_1",
            scaffolding_config={"scaffolding_level": "auto", "enabled": False},
        )
    assert res.success is True
    assert res.analytics["scaffolding_outcome"] == "disabled"
