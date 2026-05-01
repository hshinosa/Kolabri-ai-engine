"""
Comprehensive Unit Tests for ExportService and MongoDBLogger
=============================================================
100% coverage target for:
  - app/services/export_service.py
  - app/services/mongodb_logger.py

All MongoDB (Motor) calls are mocked. No real DB required.

Run from ai-engine/:
  python -m pytest ../tests/test_unit/test_export_and_mongo.py -v

Or with coverage:
  python -m pytest ../tests/test_unit/test_export_and_mongo.py \
      --cov=app.services.export_service --cov=app.services.mongodb_logger \
      --cov-report=term-missing --cov-branch
"""

import csv
import io
import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from datetime import datetime
from bson import ObjectId

# Ensure ai-engine is on sys.path so `app` can be imported from any cwd
_AI_ENGINE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "ai-engine")
)
if _AI_ENGINE not in sys.path:
    sys.path.insert(0, _AI_ENGINE)


# =============================================================================
# MongoDBLogger Tests
# =============================================================================


@pytest.mark.unit
class TestMongoDBLoggerConnect:
    """Tests for MongoDBLogger.connect() — all branches."""

    @pytest.mark.asyncio
    async def test_connect_disabled_noop(self):
        """When enabled=False, connect() returns immediately without creating client."""
        with patch("app.services.mongodb_logger.settings") as mock_settings:
            mock_settings.ENABLE_MONGODB_LOGGING = False
            from app.services.mongodb_logger import MongoDBLogger

            logger = MongoDBLogger()
            assert logger.enabled is False

            await logger.connect()

            assert logger.client is None
            assert logger.db is None

    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Successful connect: client created, ping sent, indexes created."""
        with (
            patch("app.services.mongodb_logger.settings") as mock_settings,
            patch("app.services.mongodb_logger.AsyncIOMotorClient") as MockMotor,
        ):
            mock_settings.ENABLE_MONGODB_LOGGING = True
            mock_settings.MONGO_URI = "mongodb://localhost:27017"
            mock_settings.MONGO_DB_NAME = "testdb"

            mock_client = MagicMock()
            mock_client.admin.command = AsyncMock(return_value={"ok": 1})
            mock_db = MagicMock()
            mock_db.activity_logs.create_index = AsyncMock()
            mock_db.silence_events.create_index = AsyncMock()
            mock_client.__getitem__ = MagicMock(return_value=mock_db)
            MockMotor.return_value = mock_client

            from app.services.mongodb_logger import MongoDBLogger

            logger = MongoDBLogger()
            logger.enabled = True
            await logger.connect()

            MockMotor.assert_called_once()
            assert MockMotor.call_args.args[0] == "mongodb://localhost:27017"
            mock_client.admin.command.assert_awaited_once_with("ping")
            assert mock_db.activity_logs.create_index.await_count == 2
            mock_db.silence_events.create_index.assert_awaited_once()
            assert logger.client is mock_client
            assert logger.db is mock_db
            assert logger.enabled is True

    @pytest.mark.asyncio
    async def test_connect_failure_disables_logging(self):
        """When ping raises, enabled is set to False."""
        with (
            patch("app.services.mongodb_logger.settings") as mock_settings,
            patch("app.services.mongodb_logger.AsyncIOMotorClient") as MockMotor,
        ):
            mock_settings.ENABLE_MONGODB_LOGGING = True
            mock_settings.MONGO_URI = "mongodb://localhost:27017"
            mock_settings.MONGO_DB_NAME = "testdb"

            mock_client = MagicMock()
            mock_client.admin.command = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            mock_client.__getitem__ = MagicMock(return_value=MagicMock())
            MockMotor.return_value = mock_client

            from app.services.mongodb_logger import MongoDBLogger

            logger = MongoDBLogger()
            logger.enabled = True
            await logger.connect()

            assert logger.enabled is False


@pytest.mark.unit
class TestMongoDBLoggerLogActivity:
    """Tests for MongoDBLogger.log_activity()."""

    @pytest.mark.asyncio
    async def test_log_activity_disabled_noop(self):
        """When disabled, log_activity does nothing."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = False
            logger = MongoDBLogger()
            logger.enabled = False
            logger.db = MagicMock()
            logger.db.activity_logs.insert_one = AsyncMock()

            await logger.log_activity({"CaseID": "c1"})
            logger.db.activity_logs.insert_one.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_log_activity_db_none_noop(self):
        """When db is None, log_activity does nothing (early return guard)."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = True
            logger = MongoDBLogger()
            logger.enabled = True
            logger.db = None

            await logger.log_activity({"CaseID": "c1"})
            # No exception, no call — just returns

    @pytest.mark.asyncio
    async def test_log_activity_adds_timestamp(self):
        """If entry has no Timestamp, one is added."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = True
            logger = MongoDBLogger()
            logger.enabled = True
            mock_db = MagicMock()
            mock_db.activity_logs.insert_one = AsyncMock()
            logger.db = mock_db

            entry = {"CaseID": "c1", "Activity": "Test"}
            await logger.log_activity(entry)

            call_args = mock_db.activity_logs.insert_one.call_args[0][0]
            assert "Timestamp" in call_args
            assert isinstance(call_args["Timestamp"], datetime)

    @pytest.mark.asyncio
    async def test_log_activity_preserves_existing_timestamp(self):
        """If entry already has Timestamp, it is kept."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = True
            logger = MongoDBLogger()
            logger.enabled = True
            mock_db = MagicMock()
            mock_db.activity_logs.insert_one = AsyncMock()
            logger.db = mock_db

            ts = datetime(2024, 6, 15, 12, 0, 0)
            entry = {"CaseID": "c1", "Timestamp": ts}
            await logger.log_activity(entry)

            call_args = mock_db.activity_logs.insert_one.call_args[0][0]
            assert call_args["Timestamp"] == ts

    @pytest.mark.asyncio
    async def test_log_activity_insert_failure_handled(self):
        """Exception during insert_one is caught and logged, not re-raised."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = True
            logger = MongoDBLogger()
            logger.enabled = True
            mock_db = MagicMock()
            mock_db.activity_logs.insert_one = AsyncMock(
                side_effect=Exception("write error")
            )
            logger.db = mock_db

            # Should not raise
            await logger.log_activity({"CaseID": "c1"})


@pytest.mark.unit
class TestMongoDBLoggerLogIntervention:
    """Tests for MongoDBLogger.log_intervention()."""

    @pytest.mark.asyncio
    async def test_log_intervention_builds_correct_entry(self):
        """Verify the XES entry structure built by log_intervention."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = True
            logger = MongoDBLogger()
            logger.enabled = True
            mock_db = MagicMock()
            mock_db.activity_logs.insert_one = AsyncMock()
            logger.db = mock_db

            await logger.log_intervention(
                group_id="grp1",
                intervention_type="silence",
                reason="Too quiet",
                metadata={"minutes": 10},
                session_id="3",
            )

            call_args = mock_db.activity_logs.insert_one.call_args[0][0]
            assert call_args["CaseID"] == "grp1_session_3"
            assert call_args["Activity"] == "System_Intervention_SILENCE"
            assert call_args["Resource"] == "System_Orchestrator"
            assert call_args["Lifecycle"] == "complete"
            assert call_args["Attributes"]["original_text"] == "Too quiet"
            assert call_args["Attributes"]["scaffolding_trigger"] is True
            assert call_args["Attributes"]["metadata"] == {"minutes": 10}
            assert isinstance(call_args["Timestamp"], datetime)

    @pytest.mark.asyncio
    async def test_log_intervention_default_session_id(self):
        """Default session_id is '1'."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = True
            logger = MongoDBLogger()
            logger.enabled = True
            mock_db = MagicMock()
            mock_db.activity_logs.insert_one = AsyncMock()
            logger.db = mock_db

            await logger.log_intervention(
                group_id="grp2",
                intervention_type="dominance",
                reason="Uneven participation",
                metadata={},
            )

            call_args = mock_db.activity_logs.insert_one.call_args[0][0]
            assert call_args["CaseID"] == "grp2_session_1"
            assert call_args["Activity"] == "System_Intervention_DOMINANCE"


@pytest.mark.unit
class TestMongoDBLoggerGetActivityLogs:
    """Tests for MongoDBLogger.get_activity_logs() — all filter combos."""

    def _make_logger_with_cursor(self, logs_data):
        """Helper: create a logger with a mocked cursor returning logs_data."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = True
            logger = MongoDBLogger()
            logger.enabled = True
            mock_db = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.sort.return_value = mock_cursor
            mock_cursor.limit.return_value = mock_cursor
            mock_cursor.to_list = AsyncMock(return_value=logs_data)
            mock_db.activity_logs.find.return_value = mock_cursor
            logger.db = mock_db
        return logger, mock_db

    @pytest.mark.asyncio
    async def test_get_logs_disabled_returns_empty(self):
        """When disabled, returns empty list."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = False
            logger = MongoDBLogger()
            logger.enabled = False
            result = await logger.get_activity_logs(case_id="x")
            assert result == []

    @pytest.mark.asyncio
    async def test_get_logs_db_none_returns_empty(self):
        """When db is None, returns empty list."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = True
            logger = MongoDBLogger()
            logger.enabled = True
            logger.db = None
            result = await logger.get_activity_logs(case_id="x")
            assert result == []

    @pytest.mark.asyncio
    async def test_get_logs_case_id_filter(self):
        """case_id populates query['CaseID']."""
        logger, mock_db = self._make_logger_with_cursor(
            [{"_id": ObjectId(), "CaseID": "c1", "Timestamp": datetime(2024, 1, 1)}]
        )
        result = await logger.get_activity_logs(case_id="c1")

        query = mock_db.activity_logs.find.call_args[0][0]
        assert query["CaseID"] == "c1"
        assert "Resource" not in query
        assert len(result) == 1
        assert isinstance(result[0]["_id"], str)
        assert isinstance(result[0]["Timestamp"], str)

    @pytest.mark.asyncio
    async def test_get_logs_resource_filter(self):
        """resource populates query['Resource']."""
        logger, mock_db = self._make_logger_with_cursor([])
        await logger.get_activity_logs(resource="user1")
        query = mock_db.activity_logs.find.call_args[0][0]
        assert query["Resource"] == "user1"
        assert "CaseID" not in query

    @pytest.mark.asyncio
    async def test_get_logs_both_filters(self):
        """Both case_id and resource set."""
        logger, mock_db = self._make_logger_with_cursor([])
        await logger.get_activity_logs(case_id="c1", resource="u1")
        query = mock_db.activity_logs.find.call_args[0][0]
        assert query["CaseID"] == "c1"
        assert query["Resource"] == "u1"

    @pytest.mark.asyncio
    async def test_get_logs_no_filters(self):
        """No filters → empty query dict."""
        logger, mock_db = self._make_logger_with_cursor([])
        await logger.get_activity_logs()
        query = mock_db.activity_logs.find.call_args[0][0]
        assert query == {}

    @pytest.mark.asyncio
    async def test_get_logs_legacy_chat_space_id(self):
        """Legacy kwarg chat_space_id maps to CaseID."""
        logger, mock_db = self._make_logger_with_cursor([])
        await logger.get_activity_logs(chat_space_id="legacy_cs")
        query = mock_db.activity_logs.find.call_args[0][0]
        assert query["CaseID"] == "legacy_cs"

    @pytest.mark.asyncio
    async def test_get_logs_legacy_user_id(self):
        """Legacy kwarg user_id maps to Resource."""
        logger, mock_db = self._make_logger_with_cursor([])
        await logger.get_activity_logs(user_id="legacy_u")
        query = mock_db.activity_logs.find.call_args[0][0]
        assert query["Resource"] == "legacy_u"

    @pytest.mark.asyncio
    async def test_get_logs_case_id_takes_priority_over_legacy(self):
        """case_id parameter takes priority over chat_space_id kwarg."""
        logger, mock_db = self._make_logger_with_cursor([])
        await logger.get_activity_logs(case_id="primary", chat_space_id="legacy")
        query = mock_db.activity_logs.find.call_args[0][0]
        assert query["CaseID"] == "primary"

    @pytest.mark.asyncio
    async def test_get_logs_resource_takes_priority_over_legacy(self):
        """resource parameter takes priority over user_id kwarg."""
        logger, mock_db = self._make_logger_with_cursor([])
        await logger.get_activity_logs(resource="primary_r", user_id="legacy_r")
        query = mock_db.activity_logs.find.call_args[0][0]
        assert query["Resource"] == "primary_r"

    @pytest.mark.asyncio
    async def test_get_logs_custom_limit(self):
        """limit parameter is passed through to cursor."""
        logger, mock_db = self._make_logger_with_cursor([])
        await logger.get_activity_logs(limit=50)
        mock_cursor = mock_db.activity_logs.find.return_value.sort.return_value
        mock_cursor.limit.assert_called_with(50)

    @pytest.mark.asyncio
    async def test_get_logs_timestamp_not_datetime_untouched(self):
        """Timestamp that is not a datetime instance is left as-is."""
        logger, _ = self._make_logger_with_cursor(
            [{"_id": ObjectId(), "CaseID": "c1", "Timestamp": "already_string"}]
        )
        result = await logger.get_activity_logs()
        assert result[0]["Timestamp"] == "already_string"

    @pytest.mark.asyncio
    async def test_get_logs_exception_returns_empty(self):
        """Exception during find returns empty list."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = True
            logger = MongoDBLogger()
            logger.enabled = True
            mock_db = MagicMock()
            mock_db.activity_logs.find.side_effect = Exception("query error")
            logger.db = mock_db

            result = await logger.get_activity_logs(case_id="c1")
            assert result == []


@pytest.mark.unit
class TestMongoDBLoggerExportToCsv:
    """Tests for MongoDBLogger.export_to_csv()."""

    @pytest.mark.asyncio
    async def test_export_csv_with_logs(self):
        """CSV output has correct headers and row data."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = True
            logger = MongoDBLogger()
            logger.enabled = True
            logger.db = MagicMock()

            mock_logs = [
                {
                    "_id": "1",
                    "CaseID": "case1",
                    "Activity": "Student_Message",
                    "Timestamp": "2024-01-01T00:00:00",
                    "Resource": "Student_A",
                    "Lifecycle": "complete",
                    "Attributes": {
                        "original_text": "Hello world",
                        "srl_object": "Planning",
                        "educational_category": "Cognitive",
                        "is_hot": True,
                        "lexical_variety": 0.85,
                        "scaffolding_trigger": False,
                    },
                }
            ]

            with patch.object(
                logger,
                "get_activity_logs",
                new_callable=AsyncMock,
                return_value=mock_logs,
            ):
                csv_str = await logger.export_to_csv(case_id="case1")

            reader = csv.reader(io.StringIO(csv_str))
            rows = list(reader)
            # Header
            assert rows[0] == [
                "CaseID",
                "Activity",
                "Timestamp",
                "Resource",
                "Lifecycle",
                "original_text",
                "srl_object",
                "educational_category",
                "is_hot",
                "lexical_variety",
                "scaffolding_trigger",
            ]
            # Data row
            assert rows[1][0] == "case1"
            assert rows[1][1] == "Student_Message"
            assert rows[1][5] == "Hello world"
            assert rows[1][8] == "True"
            assert rows[1][9] == "0.85"

    @pytest.mark.asyncio
    async def test_export_csv_empty_logs(self):
        """Empty logs produce header-only CSV."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = True
            logger = MongoDBLogger()
            logger.enabled = True
            logger.db = MagicMock()

            with patch.object(
                logger, "get_activity_logs", new_callable=AsyncMock, return_value=[]
            ):
                csv_str = await logger.export_to_csv()

            reader = csv.reader(io.StringIO(csv_str))
            rows = list(reader)
            assert len(rows) == 1  # header only
            assert rows[0][0] == "CaseID"

    @pytest.mark.asyncio
    async def test_export_csv_missing_attributes(self):
        """Logs with missing Attributes produce empty attribute columns."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = True
            logger = MongoDBLogger()
            logger.enabled = True
            logger.db = MagicMock()

            mock_logs = [
                {
                    "_id": "2",
                    "CaseID": "case2",
                    "Activity": "Act",
                    "Timestamp": "2024-01-01",
                    "Resource": "R",
                    "Lifecycle": "start",
                    "Attributes": {},
                }
            ]

            with patch.object(
                logger,
                "get_activity_logs",
                new_callable=AsyncMock,
                return_value=mock_logs,
            ):
                csv_str = await logger.export_to_csv(case_id="case2")

            reader = csv.reader(io.StringIO(csv_str))
            rows = list(reader)
            # Attribute columns should be empty strings
            assert rows[1][5] == ""  # original_text
            assert rows[1][8] == ""  # is_hot

    @pytest.mark.asyncio
    async def test_export_csv_no_case_id_param(self):
        """export_to_csv(case_id=None) passes None to get_activity_logs."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = True
            logger = MongoDBLogger()
            logger.enabled = True
            logger.db = MagicMock()

            with patch.object(
                logger, "get_activity_logs", new_callable=AsyncMock, return_value=[]
            ) as mock_get:
                await logger.export_to_csv()
                mock_get.assert_awaited_once_with(case_id=None, limit=10000)

    @pytest.mark.asyncio
    async def test_export_csv_log_without_attributes_key(self):
        """Logs missing Attributes key entirely still produce valid CSV rows."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = True
            logger = MongoDBLogger()
            logger.enabled = True
            logger.db = MagicMock()

            mock_logs = [
                {
                    "_id": "3",
                    "CaseID": "c3",
                    "Activity": "X",
                    "Timestamp": "2024-06-01",
                    "Resource": "R3",
                    "Lifecycle": "complete",
                    # No "Attributes" key at all
                }
            ]

            with patch.object(
                logger,
                "get_activity_logs",
                new_callable=AsyncMock,
                return_value=mock_logs,
            ):
                csv_str = await logger.export_to_csv(case_id="c3")

            reader = csv.reader(io.StringIO(csv_str))
            rows = list(reader)
            assert len(rows) == 2  # header + 1 data row
            # All attribute columns should be empty
            for col_idx in range(5, 11):
                assert rows[1][col_idx] == ""


@pytest.mark.unit
class TestMongoDBLoggerClose:
    """Tests for MongoDBLogger.close()."""

    @pytest.mark.asyncio
    async def test_close_with_client(self):
        """close() calls client.close() when client exists."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = True
            logger = MongoDBLogger()
            mock_client = MagicMock()
            logger.client = mock_client

            await logger.close()
            mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_without_client(self):
        """close() is safe when client is None."""
        from app.services.mongodb_logger import MongoDBLogger

        with patch("app.services.mongodb_logger.settings") as ms:
            ms.ENABLE_MONGODB_LOGGING = True
            logger = MongoDBLogger()
            logger.client = None
            await logger.close()  # No error


@pytest.mark.unit
class TestGetMongoLogger:
    """Test get_mongo_logger singleton."""

    def test_get_mongo_logger_singleton(self):
        """get_mongo_logger returns same instance on repeated calls."""
        import app.services.mongodb_logger as mod

        mod._mongo_logger = None  # reset

        l1 = mod.get_mongo_logger()
        l2 = mod.get_mongo_logger()
        assert l1 is l2

        mod._mongo_logger = None  # cleanup


# =============================================================================
# ExportService Tests
# =============================================================================


@pytest.fixture
def export_svc():
    """Create ExportService with mocked settings and Motor client."""
    with (
        patch("app.services.export_service.settings") as mock_settings,
        patch("app.services.export_service.AsyncIOMotorClient") as MockMotor,
    ):
        mock_settings.MONGO_URI = "mongodb://localhost:27017"
        mock_settings.MONGO_DB_NAME = "test_db"

        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        MockMotor.return_value = mock_client

        from app.services.export_service import ExportService

        service = ExportService()
        yield service, mock_client, mock_db


@pytest.mark.unit
class TestExportServiceInitialize:
    """Tests for ExportService.initialize() and __init__."""

    def test_init_state(self, export_svc):
        """Initial state: not initialized, no client, no db."""
        svc, _, _ = export_svc
        assert svc._initialized is False
        assert svc._client is None
        assert svc._db is None

    @pytest.mark.asyncio
    async def test_initialize_creates_connection(self, export_svc):
        """First call to initialize() creates client and db."""
        svc, mock_client, mock_db = export_svc
        await svc.initialize()
        assert svc._initialized is True
        assert svc._client is mock_client
        assert svc._db is mock_db

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, export_svc):
        """Second call to initialize() is a no-op."""
        svc, mock_client, mock_db = export_svc
        await svc.initialize()
        client_ref = svc._client
        db_ref = svc._db

        await svc.initialize()
        assert svc._client is client_ref
        assert svc._db is db_ref


@pytest.mark.unit
class TestExportServiceClose:
    """Tests for ExportService.close()."""

    @pytest.mark.asyncio
    async def test_close_with_client(self, export_svc):
        """close() calls client.close() and resets initialized flag."""
        svc, mock_client, _ = export_svc
        await svc.initialize()
        assert svc._initialized is True

        await svc.close()
        mock_client.close.assert_called_once()
        assert svc._initialized is False

    @pytest.mark.asyncio
    async def test_close_without_client(self, export_svc):
        """close() is safe when client is None."""
        svc, _, _ = export_svc
        await svc.close()  # No error, _client is None


@pytest.mark.unit
class TestExportServiceAggregateByGroup:
    """Tests for ExportService.aggregate_activity_by_group()."""

    @pytest.mark.asyncio
    async def test_aggregate_group_multi_user(self, export_svc):
        """Multiple users with varying metrics, sorted by engagement_score desc."""
        svc, _, mock_db = export_svc

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "Resource": "Alice",
                    "Attributes": {
                        "original_text": "I think we should analyze the data carefully",
                        "is_hot": True,
                        "lexical_variety": 0.9,
                    },
                },
                {
                    "Resource": "Alice",
                    "Attributes": {
                        "original_text": "Let me check again",
                        "is_hot": False,
                        "lexical_variety": 0.5,
                    },
                },
                {
                    "Resource": "Bob",
                    "Attributes": {
                        "original_text": "ok",
                        "is_hot": False,
                        "lexical_variety": 0.1,
                    },
                },
            ]
        )
        mock_db.activity_logs.find.return_value = mock_cursor

        result = await svc.aggregate_activity_by_group("grp1")

        assert len(result) == 2
        # Alice: 2 msgs, hot_count=1, total_lex=1.4
        alice = next(r for r in result if r["user_id"] == "Alice")
        assert alice["message_count"] == 2
        assert alice["word_count"] == 12  # 8+4
        assert alice["hot_count"] == 1
        assert alice["avg_lexical_variety"] == 0.7  # 1.4/2
        # engagement = (50*0.4) + (0.7*60) = 20 + 42 = 62.0
        assert alice["engagement_score"] == 62.0

        # Bob: 1 msg, hot_count=0
        bob = next(r for r in result if r["user_id"] == "Bob")
        assert bob["message_count"] == 1
        assert bob["word_count"] == 1
        assert bob["hot_count"] == 0
        # engagement = (0*0.4) + (0.1*60) = 6.0
        assert bob["engagement_score"] == 6.0

        # Sorted descending by engagement_score
        assert result[0]["engagement_score"] >= result[1]["engagement_score"]

    @pytest.mark.asyncio
    async def test_aggregate_group_empty(self, export_svc):
        """No logs → empty result list."""
        svc, _, mock_db = export_svc

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db.activity_logs.find.return_value = mock_cursor

        result = await svc.aggregate_activity_by_group("empty_grp")
        assert result == []

    @pytest.mark.asyncio
    async def test_aggregate_group_unknown_resource(self, export_svc):
        """Log without Resource defaults to 'unknown'."""
        svc, _, mock_db = export_svc

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "Attributes": {
                        "original_text": "hello",
                        "is_hot": False,
                        "lexical_variety": 0.3,
                    }
                }
            ]
        )
        mock_db.activity_logs.find.return_value = mock_cursor

        result = await svc.aggregate_activity_by_group("grp_x")
        assert len(result) == 1
        assert result[0]["user_id"] == "unknown"
        assert result[0]["name"] == "unknown"

    @pytest.mark.asyncio
    async def test_aggregate_group_missing_attributes(self, export_svc):
        """Log with empty Attributes: original_text='', is_hot absent, lexical_variety absent."""
        svc, _, mock_db = export_svc

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[{"Resource": "X", "Attributes": {}}]
        )
        mock_db.activity_logs.find.return_value = mock_cursor

        result = await svc.aggregate_activity_by_group("grp_y")
        assert result[0]["message_count"] == 1
        assert result[0]["word_count"] == 0  # "".split() = [] → len = 0
        assert result[0]["hot_count"] == 0
        assert result[0]["total_lexical_variety"] == 0.0

    @pytest.mark.asyncio
    async def test_aggregate_group_no_attributes_key(self, export_svc):
        """Log missing Attributes key entirely."""
        svc, _, mock_db = export_svc

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[{"Resource": "Y"}])
        mock_db.activity_logs.find.return_value = mock_cursor

        result = await svc.aggregate_activity_by_group("grp_z")
        assert result[0]["message_count"] == 1
        assert result[0]["hot_count"] == 0

    @pytest.mark.asyncio
    async def test_aggregate_group_db_error_raises(self, export_svc):
        """Exception during aggregation is re-raised."""
        svc, _, mock_db = export_svc

        mock_db.activity_logs.find.side_effect = Exception("DB error")

        with pytest.raises(Exception, match="DB error"):
            await svc.aggregate_activity_by_group("fail_grp")

    @pytest.mark.asyncio
    async def test_aggregate_group_query_uses_regex(self, export_svc):
        """Verify the regex query pattern ^{group_id}."""
        svc, _, mock_db = export_svc

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db.activity_logs.find.return_value = mock_cursor

        await svc.aggregate_activity_by_group("myGroup")

        call_args = mock_db.activity_logs.find.call_args[0][0]
        assert call_args["CaseID"] == {"$regex": "^myGroup"}
        assert call_args["Activity"] == "Student_Message"


@pytest.mark.unit
class TestExportServiceAggregateByChatSpace:
    """Tests for ExportService.aggregate_activity_by_chat_space()."""

    @pytest.mark.asyncio
    async def test_aggregate_chat_space_multi_user(self, export_svc):
        """Multiple users, sorted by message_count desc."""
        svc, _, mock_db = export_svc

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "Resource": "U1",
                    "Attributes": {
                        "original_text": "a b c",
                        "is_hot": True,
                        "lexical_variety": 0.8,
                    },
                },
                {
                    "Resource": "U1",
                    "Attributes": {
                        "original_text": "d e",
                        "is_hot": False,
                        "lexical_variety": 0.6,
                    },
                },
                {
                    "Resource": "U2",
                    "Attributes": {
                        "original_text": "f",
                        "is_hot": False,
                        "lexical_variety": 0.2,
                    },
                },
            ]
        )
        mock_db.activity_logs.find.return_value = mock_cursor

        result = await svc.aggregate_activity_by_chat_space("cs1")

        assert len(result) == 2
        # Sorted by message_count desc, U1 (2) before U2 (1)
        assert result[0]["user_id"] == "U1"
        assert result[0]["message_count"] == 2
        assert result[0]["word_count"] == 5  # 3+2
        assert result[0]["hot_count"] == 1
        assert result[0]["avg_lexical_variety"] == 0.7  # (0.8+0.6)/2

        assert result[1]["user_id"] == "U2"
        assert result[1]["message_count"] == 1

    @pytest.mark.asyncio
    async def test_aggregate_chat_space_empty(self, export_svc):
        """No logs → empty result."""
        svc, _, mock_db = export_svc

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db.activity_logs.find.return_value = mock_cursor

        result = await svc.aggregate_activity_by_chat_space("cs_empty")
        assert result == []

    @pytest.mark.asyncio
    async def test_aggregate_chat_space_error_raises(self, export_svc):
        """Exception during aggregation is re-raised."""
        svc, _, mock_db = export_svc

        mock_db.activity_logs.find.side_effect = Exception("timeout")

        with pytest.raises(Exception, match="timeout"):
            await svc.aggregate_activity_by_chat_space("cs_fail")

    @pytest.mark.asyncio
    async def test_aggregate_chat_space_query_exact_match(self, export_svc):
        """CaseID is exact match (not regex like group)."""
        svc, _, mock_db = export_svc

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db.activity_logs.find.return_value = mock_cursor

        await svc.aggregate_activity_by_chat_space("exact_cs_id")

        call_args = mock_db.activity_logs.find.call_args[0][0]
        assert call_args["CaseID"] == "exact_cs_id"
        assert call_args["Activity"] == "Student_Message"

    @pytest.mark.asyncio
    async def test_aggregate_chat_space_unknown_resource(self, export_svc):
        """Missing Resource defaults to 'unknown'."""
        svc, _, mock_db = export_svc

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[{"Attributes": {"original_text": "hi"}}]
        )
        mock_db.activity_logs.find.return_value = mock_cursor

        result = await svc.aggregate_activity_by_chat_space("cs_x")
        assert result[0]["user_id"] == "unknown"

    @pytest.mark.asyncio
    async def test_aggregate_chat_space_missing_attributes(self, export_svc):
        """Log with empty Attributes in chat space aggregation."""
        svc, _, mock_db = export_svc

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[{"Resource": "U3", "Attributes": {}}]
        )
        mock_db.activity_logs.find.return_value = mock_cursor

        result = await svc.aggregate_activity_by_chat_space("cs_y")
        assert result[0]["message_count"] == 1
        assert result[0]["word_count"] == 0
        assert result[0]["hot_count"] == 0
        assert result[0]["avg_lexical_variety"] == 0.0


@pytest.mark.unit
class TestExportServiceGenerateCsvString:
    """Tests for ExportService.generate_csv_string()."""

    @pytest.fixture
    def svc(self, export_svc):
        svc, _, _ = export_svc
        return svc

    def test_csv_detailed_mode(self, svc):
        """include_detailed=True produces 12-column header."""
        metrics = [
            {
                "name": "Student A",
                "user_id": "u1",
                "message_count": 10,
                "word_count": 200,
                "hot_count": 4,
                "cognitive_count": 3,
                "behavioral_count": 5,
                "emotional_count": 2,
                "avg_lexical_variety": 0.75,
                "engagement_score": 85.5,
            }
        ]

        csv_str = svc.generate_csv_string(metrics, include_detailed=True)
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)

        # Header
        assert rows[0] == [
            "Student Name",
            "User ID",
            "Message Count",
            "Total Words",
            "Avg Words/Message",
            "HOT Count",
            "HOT Percentage",
            "Cognitive Messages",
            "Behavioral Messages",
            "Emotional Messages",
            "Avg Lexical Variety",
            "Engagement Score",
        ]
        # Data row
        assert rows[1][0] == "Student A"
        assert rows[1][1] == "u1"
        assert rows[1][2] == "10"
        assert rows[1][3] == "200"
        assert rows[1][4] == "20.0"  # 200/10
        assert rows[1][5] == "4"
        assert rows[1][6] == "40.0"  # (4/10)*100
        assert rows[1][7] == "3"  # cognitive
        assert rows[1][8] == "5"  # behavioral
        assert rows[1][9] == "2"  # emotional
        assert rows[1][10] == "0.75"
        assert rows[1][11] == "85.5"
        # Summary row
        assert rows[2][0] == "--- TOTAL ---"
        assert rows[2][2] == "10"  # total messages
        assert rows[2][3] == "200"  # total words
        assert rows[2][5] == "4"  # total hot

    def test_csv_simple_mode(self, svc):
        """include_detailed=False produces 5-column header."""
        metrics = [
            {
                "name": "Student B",
                "message_count": 3,
                "word_count": 60,
                "hot_count": 1,
                "engagement_score": 40.0,
            }
        ]

        csv_str = svc.generate_csv_string(metrics, include_detailed=False)
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)

        assert rows[0] == [
            "Student Name",
            "Message Count",
            "Total Words",
            "HOT Count",
            "Engagement Score",
        ]
        assert rows[1][0] == "Student B"
        assert rows[1][1] == "3"
        # Summary
        assert rows[2][0] == "--- TOTAL ---"
        assert rows[2][1] == "3"

    def test_csv_empty_metrics(self, svc):
        """Empty user_metrics → header only, no summary row."""
        csv_str = svc.generate_csv_string([], include_detailed=True)
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)

        assert len(rows) == 1  # header only
        assert "--- TOTAL ---" not in csv_str

    def test_csv_zero_message_count(self, svc):
        """Zero message_count → avg_words=0, hot_percentage=0."""
        metrics = [
            {
                "name": "Ghost",
                "user_id": "g1",
                "message_count": 0,
                "word_count": 0,
                "hot_count": 0,
                "engagement_score": 0.0,
            }
        ]

        csv_str = svc.generate_csv_string(metrics, include_detailed=True)
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)

        assert rows[1][4] == "0"  # avg_words = 0
        assert rows[1][6] == "0"  # hot_percentage = 0

    def test_csv_missing_optional_fields(self, svc):
        """Missing optional fields use defaults from .get()."""
        metrics = [
            {
                "message_count": 5,
                "word_count": 100,
                "hot_count": 2,
            }
        ]

        csv_str = svc.generate_csv_string(metrics, include_detailed=True)
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)

        assert rows[1][0] == "Unknown"  # name default
        assert rows[1][1] == "N/A"  # user_id default
        assert rows[1][7] == "0"  # cognitive_count default
        assert rows[1][10] == "0.0"  # avg_lexical_variety default
        assert rows[1][11] == "0.0"  # engagement_score default

    def test_csv_multiple_students_summary(self, svc):
        """Summary row aggregates across multiple students."""
        metrics = [
            {
                "name": "A",
                "user_id": "a",
                "message_count": 5,
                "word_count": 100,
                "hot_count": 2,
                "cognitive_count": 1,
                "behavioral_count": 2,
                "emotional_count": 1,
                "avg_lexical_variety": 0.8,
                "engagement_score": 70.0,
            },
            {
                "name": "B",
                "user_id": "b",
                "message_count": 3,
                "word_count": 50,
                "hot_count": 1,
                "cognitive_count": 2,
                "behavioral_count": 0,
                "emotional_count": 1,
                "avg_lexical_variety": 0.6,
                "engagement_score": 50.0,
            },
        ]

        csv_str = svc.generate_csv_string(metrics, include_detailed=True)
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)

        summary = rows[3]  # header + 2 data + summary
        assert summary[0] == "--- TOTAL ---"
        assert summary[2] == "8"  # 5+3 total messages
        assert summary[3] == "150"  # 100+50 total words
        assert float(summary[4]) == round(150 / 8, 2)  # avg words
        assert summary[5] == "3"  # 2+1 total hot
        assert float(summary[6]) == round((3 / 8) * 100, 2)  # hot pct
        assert summary[7] == "3"  # 1+2 cognitive
        assert summary[8] == "2"  # 2+0 behavioral
        assert summary[9] == "2"  # 1+1 emotional
        assert float(summary[11]) == round((70.0 + 50.0) / 2, 2)  # avg engagement

    def test_csv_simple_multiple_summary(self, svc):
        """Summary row in simple mode."""
        metrics = [
            {
                "name": "A",
                "message_count": 4,
                "word_count": 80,
                "hot_count": 2,
                "engagement_score": 60.0,
            },
            {
                "name": "B",
                "message_count": 6,
                "word_count": 120,
                "hot_count": 3,
                "engagement_score": 80.0,
            },
        ]

        csv_str = svc.generate_csv_string(metrics, include_detailed=False)
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)

        summary = rows[3]
        assert summary[0] == "--- TOTAL ---"
        assert summary[1] == "10"  # 4+6
        assert summary[2] == "200"  # 80+120
        assert summary[3] == "5"  # 2+3
        assert float(summary[4]) == round((60.0 + 80.0) / 2, 2)

    def test_csv_summary_zero_total_messages_detailed(self, svc):
        """Summary with total_messages=0 in detailed mode avoids division by zero."""
        metrics = [
            {
                "name": "Z",
                "user_id": "z",
                "message_count": 0,
                "word_count": 0,
                "hot_count": 0,
                "engagement_score": 0.0,
            }
        ]

        csv_str = svc.generate_csv_string(metrics, include_detailed=True)
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)

        summary = rows[2]
        assert summary[4] == "0"  # avg words/msg when total_messages=0
        assert summary[6] == "0"  # hot pct when total_messages=0

    def test_csv_empty_simple_mode(self, svc):
        """Empty metrics in simple mode produces header only."""
        csv_str = svc.generate_csv_string([], include_detailed=False)
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)

        assert len(rows) == 1
        assert rows[0] == [
            "Student Name",
            "Message Count",
            "Total Words",
            "HOT Count",
            "Engagement Score",
        ]

    def test_csv_simple_zero_total_messages_summary(self, svc):
        """Summary with total_messages=0 in simple mode."""
        metrics = [
            {
                "name": "Zero",
                "message_count": 0,
                "word_count": 0,
                "hot_count": 0,
                "engagement_score": 0.0,
            }
        ]

        csv_str = svc.generate_csv_string(metrics, include_detailed=False)
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)

        # Summary row exists (user_metrics is non-empty)
        assert rows[2][0] == "--- TOTAL ---"


@pytest.mark.unit
class TestExportServiceGroupActivityDetailed:
    """Tests for ExportService.export_group_activity_detailed()."""

    @pytest.mark.asyncio
    async def test_group_detailed_export(self, export_svc):
        """Full export with multiple students and student-change separators."""
        svc, _, mock_db = export_svc

        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "Resource": "Alice",
                    "CaseID": "grp1_session_1",
                    "Timestamp": "2024-01-01T10:00:00",
                    "Attributes": {
                        "original_text": "First message from Alice",
                        "is_hot": True,
                        "lexical_variety": 0.8,
                    },
                },
                {
                    "Resource": "Alice",
                    "CaseID": "grp1_session_1",
                    "Timestamp": "2024-01-01T10:05:00",
                    "Attributes": {
                        "original_text": "Second message",
                        "is_hot": False,
                        "lexical_variety": 0.5,
                    },
                },
                {
                    "Resource": "Bob",
                    "CaseID": "grp1_session_2",
                    "Timestamp": "2024-01-01T10:10:00",
                    "Attributes": {
                        "original_text": "Bob's contribution",
                        "is_hot": False,
                        "lexical_variety": 0.3,
                    },
                },
            ]
        )
        mock_db.activity_logs.find.return_value = mock_cursor

        csv_str = await svc.export_group_activity_detailed("grp1")

        assert "LAPORAN AKTIVITAS MAHASISWA PER KELOMPOK" in csv_str
        assert "grp1" in csv_str
        assert ">>> MAHASISWA: Alice <<<" in csv_str
        assert ">>> MAHASISWA: Bob <<<" in csv_str
        assert "First message from Alice" in csv_str
        assert "YA" in csv_str  # is_hot=True
        assert "TIDAK" in csv_str  # is_hot=False

    @pytest.mark.asyncio
    async def test_group_detailed_export_empty(self, export_svc):
        """No logs → header-only CSV with group info."""
        svc, _, mock_db = export_svc

        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db.activity_logs.find.return_value = mock_cursor

        csv_str = await svc.export_group_activity_detailed("grp_empty")

        assert "LAPORAN AKTIVITAS MAHASISWA PER KELOMPOK" in csv_str
        assert "grp_empty" in csv_str
        assert ">>> MAHASISWA" not in csv_str

    @pytest.mark.asyncio
    async def test_group_detailed_missing_attrs(self, export_svc):
        """Log with missing Attributes key."""
        svc, _, mock_db = export_svc

        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "Resource": "Solo",
                    "CaseID": "grp1_session_1",
                    "Timestamp": "2024-01-01T10:00:00",
                    "Attributes": {},
                }
            ]
        )
        mock_db.activity_logs.find.return_value = mock_cursor

        csv_str = await svc.export_group_activity_detailed("grp1")
        assert ">>> MAHASISWA: Solo <<<" in csv_str
        assert "TIDAK" in csv_str  # is_hot defaults to falsy → "TIDAK"

    @pytest.mark.asyncio
    async def test_group_detailed_text_truncation(self, export_svc):
        """Text longer than 100 chars is truncated in CSV."""
        svc, _, mock_db = export_svc

        long_text = "A" * 200

        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "Resource": "LongWriter",
                    "CaseID": "grp1_session_1",
                    "Timestamp": "2024-01-01T10:00:00",
                    "Attributes": {
                        "original_text": long_text,
                        "is_hot": False,
                        "lexical_variety": 0.5,
                    },
                }
            ]
        )
        mock_db.activity_logs.find.return_value = mock_cursor

        csv_str = await svc.export_group_activity_detailed("grp1")
        # The full 200-char text should not appear; only first 100
        assert "A" * 200 not in csv_str
        assert "A" * 100 in csv_str

    @pytest.mark.asyncio
    async def test_group_detailed_sort_called(self, export_svc):
        """Verify sort is called with Resource ascending, Timestamp ascending."""
        svc, _, mock_db = export_svc

        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db.activity_logs.find.return_value = mock_cursor

        await svc.export_group_activity_detailed("grp1")

        mock_cursor.sort.assert_called_once_with([("Resource", 1), ("Timestamp", 1)])

    @pytest.mark.asyncio
    async def test_group_detailed_missing_resource(self, export_svc):
        """Log without Resource key defaults to 'unknown'."""
        svc, _, mock_db = export_svc

        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "CaseID": "grp1_session_1",
                    "Timestamp": "2024-01-01T10:00:00",
                    "Attributes": {"original_text": "hello"},
                }
            ]
        )
        mock_db.activity_logs.find.return_value = mock_cursor

        csv_str = await svc.export_group_activity_detailed("grp1")
        assert ">>> MAHASISWA: unknown <<<" in csv_str


@pytest.mark.unit
class TestExportServiceChatSpaceActivity:
    """Tests for ExportService.export_chat_space_activity()."""

    @pytest.mark.asyncio
    async def test_export_chat_space_returns_csv(self, export_svc):
        """export_chat_space_activity delegates to aggregate + generate_csv_string."""
        svc, _, mock_db = export_svc

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "Resource": "U1",
                    "Attributes": {
                        "original_text": "hello world",
                        "is_hot": True,
                        "lexical_variety": 0.9,
                    },
                }
            ]
        )
        mock_db.activity_logs.find.return_value = mock_cursor

        csv_str = await svc.export_chat_space_activity("cs1", include_detailed=True)

        assert "Student Name" in csv_str
        assert "U1" in csv_str
        assert "--- TOTAL ---" in csv_str

    @pytest.mark.asyncio
    async def test_export_chat_space_simple_mode(self, export_svc):
        """include_detailed=False produces simple CSV."""
        svc, _, mock_db = export_svc

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "Resource": "U2",
                    "Attributes": {
                        "original_text": "msg",
                        "is_hot": False,
                        "lexical_variety": 0.4,
                    },
                }
            ]
        )
        mock_db.activity_logs.find.return_value = mock_cursor

        csv_str = await svc.export_chat_space_activity("cs2", include_detailed=False)

        # Simple mode does not have "User ID" column
        assert "User ID" not in csv_str
        assert "U2" in csv_str

    @pytest.mark.asyncio
    async def test_export_chat_space_empty(self, export_svc):
        """Empty chat space → header-only CSV."""
        svc, _, mock_db = export_svc

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db.activity_logs.find.return_value = mock_cursor

        csv_str = await svc.export_chat_space_activity("cs_empty")

        assert "Student Name" in csv_str
        assert "--- TOTAL ---" not in csv_str


@pytest.mark.unit
class TestGetExportService:
    """Test get_export_service singleton."""

    def test_singleton(self):
        """get_export_service returns same instance on repeated calls."""
        import app.services.export_service as mod

        mod._export_service = None  # reset

        with patch("app.services.export_service.settings"):
            s1 = mod.get_export_service()
            s2 = mod.get_export_service()
            assert s1 is s2

        mod._export_service = None  # cleanup
