from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.mongodb_logger import MongoDBLogger


@pytest.mark.asyncio
async def test_mongodb_logger_full():
    with patch("app.services.mongodb_logger.PIIDetector") as mock_pii:
        mock_pii.return_value.mask.side_effect = lambda text: text
        logger = MongoDBLogger()
        logger.enabled = True
        logger.db = MagicMock()
        logger.db.activity_logs.insert_one = AsyncMock()

        await logger.log_activity({"CaseID": "c1", "Activity": "Test", "Attributes": {"original_text": "hello"}})

        logger.db.activity_logs.insert_one.assert_awaited_once()
