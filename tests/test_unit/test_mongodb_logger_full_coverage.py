"""Focused tests for current MongoDB logger behavior."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import mongodb_logger as mongo_module
from app.services.mongodb_logger import MongoDBLogger, get_mongo_logger


@pytest.fixture
def mongo_logger():
    with patch("app.services.mongodb_logger.PIIDetector") as mock_pii:
        mock_pii.return_value.mask.side_effect = lambda text: text
        yield MongoDBLogger()


class TestMongoDBLoggerFull:
    def test_init(self, mongo_logger):
        assert mongo_logger.client is None
        assert mongo_logger.db is None

    @pytest.mark.asyncio
    async def test_connect_disabled(self, mongo_logger):
        mongo_logger.enabled = False
        await mongo_logger.connect()
        assert mongo_logger.client is None

    @pytest.mark.asyncio
    async def test_connect_success(self, mongo_logger):
        mock_client = MagicMock()
        mock_client.admin.command = AsyncMock(return_value={"ok": 1})
        mock_db = MagicMock()
        mock_db.activity_logs.create_index = AsyncMock()
        mock_db.silence_events.create_index = AsyncMock()
        mock_client.__getitem__.return_value = mock_db

        with patch("app.services.mongodb_logger.AsyncIOMotorClient", return_value=mock_client):
            with patch.object(mongo_module.settings, "MONGO_URI", "mongodb://localhost"), patch.object(
                mongo_module.settings, "MONGO_DB_NAME", "test_db"
            ), patch.object(mongo_module.settings, "MONGO_MAX_POOL_SIZE", 50), patch.object(
                mongo_module.settings, "MONGO_MIN_POOL_SIZE", 10
            ), patch.object(
                mongo_module.settings, "MONGO_MAX_IDLE_TIME_MS", 30000
            ), patch.object(
                mongo_module.settings, "MONGO_CONNECT_TIMEOUT_MS", 5000
            ):
                mongo_logger.enabled = True
                await mongo_logger.connect()

        assert mongo_logger.client is mock_client
        assert mongo_logger.db is mock_db

    @pytest.mark.asyncio
    async def test_connect_exception(self, mongo_logger):
        mock_client = MagicMock()
        mock_client.admin.command = AsyncMock(side_effect=Exception("Connection failed"))

        with patch("app.services.mongodb_logger.AsyncIOMotorClient", return_value=mock_client):
            mongo_logger.enabled = True
            await mongo_logger.connect()

        assert mongo_logger.enabled is False

    @pytest.mark.asyncio
    async def test_log_activity_variants(self, mongo_logger):
        mongo_logger.enabled = True
        mongo_logger.db = MagicMock()
        mongo_logger.db.activity_logs.insert_one = AsyncMock()

        entry = {"CaseID": "test", "Activity": "Test", "Attributes": {"original_text": "hello"}}
        await mongo_logger.log_activity(entry)
        assert "Timestamp" in entry
        mongo_logger.db.activity_logs.insert_one.assert_awaited_once()

        mongo_logger.db.activity_logs.insert_one = AsyncMock(side_effect=Exception("Error"))
        await mongo_logger.log_activity({"CaseID": "test", "Activity": "Test"})

        mongo_logger.enabled = False
        await mongo_logger.log_activity({"CaseID": "test"})


    @pytest.mark.asyncio
    async def test_log_activity_with_bound_request_id(self, mongo_logger):
        mongo_logger.enabled = True
        mongo_logger.db = MagicMock()
        mongo_logger.db.activity_logs.insert_one = AsyncMock()
        with patch(
            "app.services.mongodb_logger.structlog.contextvars.get_contextvars",
            return_value={"request_id": "trace-1"},
        ):
            await mongo_logger.log_activity({"CaseID": "c1", "Activity": "Chat"})
        entry = mongo_logger.db.activity_logs.insert_one.await_args[0][0]
        assert entry["request_id"] == "trace-1"

    @pytest.mark.asyncio
    async def test_log_intervention(self, mongo_logger):
        mongo_logger.log_activity = AsyncMock()
        await mongo_logger.log_intervention("group1", "redirect", "reason", {"key": "value"}, session_id="5")
        mongo_logger.log_activity.assert_awaited_once()
        logged_entry = mongo_logger.log_activity.await_args.args[0]
        assert logged_entry["CaseID"] == "group1_session_5"

    @pytest.mark.asyncio
    async def test_get_activity_logs_and_export(self, mongo_logger):
        mongo_logger.enabled = True
        mongo_logger.db = MagicMock()
        cursor = MagicMock()
        cursor.sort.return_value = cursor
        cursor.limit.return_value = cursor
        cursor.to_list = AsyncMock(
            return_value=[
                {
                    "_id": "mock_id",
                    "CaseID": "test",
                    "Activity": "Test",
                    "Timestamp": datetime.now(),
                    "Resource": "User",
                    "Lifecycle": "complete",
                    "Attributes": {"original_text": "Test"},
                }
            ]
        )
        mongo_logger.db.activity_logs.find.return_value = cursor

        result = await mongo_logger.get_activity_logs(case_id="test")
        assert len(result) == 1
        assert isinstance(result[0]["_id"], str)

        csv_output = await mongo_logger.export_to_csv(case_id="test")
        assert "CaseID,Activity,Timestamp" in csv_output

    @pytest.mark.asyncio
    async def test_get_activity_logs_disabled_or_failure(self, mongo_logger):
        mongo_logger.enabled = False
        assert await mongo_logger.get_activity_logs(case_id="test") == []

        mongo_logger.enabled = True
        mongo_logger.db = None
        assert await mongo_logger.get_activity_logs(case_id="test") == []

        mongo_logger.db = MagicMock()
        mongo_logger.db.activity_logs.find.side_effect = Exception("boom")
        assert await mongo_logger.get_activity_logs(case_id="test") == []

    @pytest.mark.asyncio
    async def test_close(self, mongo_logger):
        mongo_logger.client = MagicMock()
        await mongo_logger.close()
        mongo_logger.client.close.assert_called_once()


class TestGetMongoLogger:
    def test_get_mongo_logger_singleton(self):
        mongo_module._mongo_logger = None
        with patch("app.services.mongodb_logger.PIIDetector") as mock_pii:
            mock_pii.return_value.mask.side_effect = lambda text: text
            logger1 = get_mongo_logger()
            logger2 = get_mongo_logger()
        assert logger1 is logger2
