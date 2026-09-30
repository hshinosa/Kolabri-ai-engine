import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.orchestration import Orchestrator

@pytest.fixture
def mock_services():
    return {
        'rag': AsyncMock(),
        'analyzer': MagicMock(),
        'intervention': MagicMock(),
        'pm_logger': MagicMock(),
        'goal_validator': MagicMock(),
        'logic_listener': AsyncMock(),
        'notification_service': AsyncMock(),
    }

@pytest.fixture
def orchestrator(mock_services):
    with patch('app.services.orchestration.get_mongo_logger') as mock_mongo,          patch('app.services.orchestration.get_plan_vs_reality_analyzer'),          patch('app.services.orchestration.get_anomaly_detector'):
        mock_mongo.return_value = MagicMock()
        mock_mongo.return_value.log_activity = AsyncMock()
        mock_mongo.return_value.log_intervention = AsyncMock()
        mock_mongo.return_value.get_activity_logs = AsyncMock(return_value=[])
        return Orchestrator(**mock_services)
@pytest.mark.asyncio
async def test_dashboard_data(orchestrator):
    orchestrator.mongo_logger.get_activity_logs = AsyncMock(return_value=[])
    res = await orchestrator.get_group_dashboard_data('group1')
    assert res['group_id'] == 'group1'