import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from app.services.orchestration import Orchestrator
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
async def test_validate_goal(orchestrator, mock_services):
    mock_services["goal_validator"].validate_goal.return_value = MagicMock(
        is_valid=True, score=1.0, feedback="Good", missing_criteria=[], details={}
    )
    mock_services["goal_validator"].generate_socratic_hint.return_value = "Hint"

    res = await orchestrator.validate_goal("Target saya lulus", "u1", "group1")
    assert res["is_valid"] is True
    assert res["socratic_hint"] == "Hint"


