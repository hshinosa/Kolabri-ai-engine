"""Tests for app/utils/logger.py - ProcessMiningLogger"""

import csv
import os
import pytest
from pathlib import Path
from unittest.mock import patch

from app.utils.logger import (
    ProcessMiningLogger,
    ActivityType,
    Lifecycle,
    EventLogEntry,
)


@pytest.fixture
def tmp_log_dir(tmp_path):
    return str(tmp_path / "event_logs")


@pytest.fixture
def pm_logger(tmp_log_dir):
    return ProcessMiningLogger(log_dir=tmp_log_dir)


class TestProcessMiningLoggerInit:
    def test_creates_log_directory(self, tmp_log_dir):
        ProcessMiningLogger(log_dir=tmp_log_dir)
        assert Path(tmp_log_dir).exists()

    def test_creates_csv_with_header(self, pm_logger, tmp_log_dir):
        log_file = Path(tmp_log_dir) / "event_logs.csv"
        assert log_file.exists()

        with open(log_file, "r") as f:
            reader = csv.reader(f)
            header = next(reader)

        assert "CaseID" in header
        assert "Activity" in header
        assert "Timestamp" in header
        assert "Resource" in header


class TestLogEvent:
    def test_log_basic_event(self, pm_logger, tmp_log_dir):
        entry = pm_logger.log_event(
            case_id="group_1", activity="Student_Message", resource="user_123"
        )

        assert isinstance(entry, EventLogEntry)
        assert entry.case_id == "group_1"
        assert entry.activity == "Student_Message"
        assert entry.resource == "user_123"
        assert entry.lifecycle == Lifecycle.COMPLETE

    def test_log_event_writes_to_csv(self, pm_logger, tmp_log_dir):
        pm_logger.log_event(
            case_id="group_1",
            activity="Student_Message",
            resource="user_123",
            course_id="course_A",
            chat_room_id="room_1",
            topic="AI Ethics",
            engagement_type="Cognitive",
            lexical_variety=0.75,
            is_hot=True,
            message_length=150,
        )

        log_file = Path(tmp_log_dir) / "event_logs.csv"
        with open(log_file, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["CaseID"] == "group_1"
        assert rows[0]["Activity"] == "Student_Message"
        assert rows[0]["Resource"] == "user_123"
        assert rows[0]["CourseID"] == "course_A"
        assert rows[0]["Topic"] == "AI Ethics"
        assert rows[0]["LexicalVariety"] == "0.750"
        assert rows[0]["IsHOT"] == "True"
        assert rows[0]["MessageLength"] == "150"

    def test_log_event_with_extra_attributes(self, pm_logger, tmp_log_dir):
        pm_logger.log_event(
            case_id="g1",
            activity="Bot_Response",
            resource="AI_Agent",
            extra_attributes={"confidence": 0.95},
        )

        log_file = Path(tmp_log_dir) / "event_logs.csv"
        with open(log_file, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert "confidence" in rows[0]["ExtraAttributes"]

    def test_log_event_redacts_credential_in_extra_attributes(
        self, pm_logger, tmp_log_dir
    ):
        pm_logger.log_event(
            case_id="g1",
            activity="Bot_Response",
            resource="AI_Agent",
            extra_attributes={
                "provider_context": {"auth": {"credential": "sk-secret-123"}}
            },
        )

        log_file = Path(tmp_log_dir) / "event_logs.csv"
        with open(log_file, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert "[REDACTED]" in rows[0]["ExtraAttributes"]
        assert "sk-secret-123" not in rows[0]["ExtraAttributes"]

    def test_log_event_handles_write_error(self, pm_logger):
        pm_logger.log_file = Path("/nonexistent/path/log.csv")
        entry = pm_logger.log_event(case_id="g1", activity="test", resource="u1")
        assert entry is not None


class TestLogStudentMessage:
    def test_log_student_message(self, pm_logger, tmp_log_dir):
        entry = pm_logger.log_student_message(
            group_id="group_1",
            user_id="student_1",
            message_length=200,
            course_id="course_A",
            topic="Machine Learning",
            is_hot=True,
            lexical_variety=0.8,
        )

        assert entry.activity == ActivityType.STUDENT_MESSAGE.value
        assert entry.case_id == "group_1"
        assert entry.resource == "student_1"


class TestLogBotResponse:
    def test_log_bot_fetch(self, pm_logger):
        entry = pm_logger.log_bot_response(
            group_id="g1", action_taken="FETCH", response_length=500
        )
        assert entry.activity == ActivityType.BOT_FETCH.value

    def test_log_bot_no_fetch(self, pm_logger):
        entry = pm_logger.log_bot_response(
            group_id="g1", action_taken="NO_FETCH", response_length=300
        )
        assert entry.activity == ActivityType.BOT_NO_FETCH.value


class TestLogIntervention:
    def test_log_intervention(self, pm_logger):
        entry = pm_logger.log_intervention(
            group_id="g1",
            intervention_type="silence",
            trigger_reason="5min_no_activity",
            course_id="c1",
        )
        assert entry.activity == ActivityType.SYSTEM_INTERVENTION_TRIGGER.value
        assert entry.resource == "Orchestrator"


class TestGetLogsForCase:
    def test_get_logs_for_existing_case(self, pm_logger):
        pm_logger.log_event(case_id="g1", activity="A1", resource="u1")
        pm_logger.log_event(case_id="g2", activity="A2", resource="u2")
        pm_logger.log_event(case_id="g1", activity="A3", resource="u3")

        logs = pm_logger.get_logs_for_case("g1")
        assert len(logs) == 2
        assert all(log["CaseID"] == "g1" for log in logs)

    def test_get_logs_for_missing_case(self, pm_logger):
        logs = pm_logger.get_logs_for_case("nonexistent")
        assert logs == []

    def test_get_logs_file_not_found(self, pm_logger):
        pm_logger.log_file = Path("/nonexistent/log.csv")
        logs = pm_logger.get_logs_for_case("g1")
        assert logs == []


class TestExportForProm:
    def test_export_creates_file(self, pm_logger, tmp_log_dir):
        pm_logger.log_event(case_id="g1", activity="A1", resource="u1")

        output = pm_logger.export_for_prom()
        assert Path(output).exists()

        with open(output, "r") as f:
            reader = csv.reader(f)
            header = next(reader)

        assert header == [
            "case:concept:name",
            "concept:name",
            "time:timestamp",
            "org:resource",
        ]

    def test_export_custom_path(self, pm_logger, tmp_log_dir):
        pm_logger.log_event(case_id="g1", activity="A1", resource="u1")

        custom_path = str(Path(tmp_log_dir) / "custom_export.csv")
        output = pm_logger.export_for_prom(output_file=custom_path)
        assert output == custom_path
        assert Path(custom_path).exists()

    def test_export_contains_data(self, pm_logger, tmp_log_dir):
        pm_logger.log_event(case_id="g1", activity="A1", resource="u1")
        pm_logger.log_event(case_id="g2", activity="A2", resource="u2")

        output = pm_logger.export_for_prom()

        with open(output, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]["case:concept:name"] == "g1"
        assert rows[0]["concept:name"] == "A1"

    def test_export_error_raises(self, pm_logger):
        pm_logger.log_file = Path("/nonexistent/log.csv")
        with pytest.raises(Exception):
            pm_logger.export_for_prom()


class TestGetStatistics:
    def test_empty_stats(self, pm_logger):
        stats = pm_logger.get_statistics()
        assert stats["total_events"] == 0
        assert stats["unique_cases"] == 0
        assert stats["unique_resources"] == 0

    def test_stats_with_events(self, pm_logger):
        pm_logger.log_event(case_id="g1", activity="A1", resource="u1")
        pm_logger.log_event(case_id="g1", activity="A2", resource="u2")
        pm_logger.log_event(case_id="g2", activity="A1", resource="u1")
        pm_logger.log_event(case_id="g1", activity="A1", resource="u1", is_hot=True)

        stats = pm_logger.get_statistics()
        assert stats["total_events"] == 4
        assert stats["unique_cases"] == 2
        assert stats["unique_resources"] == 2
        assert stats["activity_counts"]["A1"] == 3
        assert stats["activity_counts"]["A2"] == 1
        assert stats["hot_count"] == 1

    def test_stats_file_not_found(self, pm_logger):
        pm_logger.log_file = Path("/nonexistent/log.csv")
        stats = pm_logger.get_statistics()
        assert stats["total_events"] == 0


class TestModuleFunctions:
    def test_get_process_mining_logger_singleton(self, tmp_path):
        import app.utils.logger as module

        module._pm_logger = None

        with patch.object(ProcessMiningLogger, "__init__", return_value=None):
            logger1 = module.get_process_mining_logger()
            logger2 = module.get_process_mining_logger()
            assert logger1 is logger2

        module._pm_logger = None

    def test_log_event_for_mining(self, tmp_log_dir):
        import app.utils.logger as module

        module._pm_logger = ProcessMiningLogger(log_dir=tmp_log_dir)

        entry = module.log_event_for_mining(
            case_id="g1",
            activity="Student_Message",
            resource="u1",
            lifecycle="complete",
        )

        assert entry.case_id == "g1"
        assert entry.lifecycle == Lifecycle.COMPLETE

        module._pm_logger = None


class TestActivityType:
    def test_student_activities(self):
        assert ActivityType.STUDENT_MESSAGE.value == "Student_Message"
        assert ActivityType.STUDENT_QUESTION.value == "Student_Question"

    def test_bot_activities(self):
        assert ActivityType.BOT_FETCH.value == "Bot_FETCH"
        assert ActivityType.BOT_NO_FETCH.value == "Bot_NO_FETCH"


class TestLifecycle:
    def test_lifecycle_values(self):
        assert Lifecycle.START.value == "start"
        assert Lifecycle.COMPLETE.value == "complete"
        assert Lifecycle.SUSPEND.value == "suspend"
        assert Lifecycle.RESUME.value == "resume"
        assert Lifecycle.ABORT.value == "abort"
