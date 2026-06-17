"""
Process Mining Event Logger
===========================
Structured event logging following Educational Process Mining (EPM) standards.
Supports XES conversion for analytical tools like ProM and Disco.
"""

import csv
import os
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.utils.sensitive_data import sanitize_sensitive_data

logger = get_logger(__name__)


class ActivityType(str, Enum):
    """Standard activity types for process mining classification."""

    # Student activities
    STUDENT_MESSAGE = "Student_Message"
    STUDENT_QUESTION = "Student_Question"
    STUDENT_ANSWER = "Student_Answer"
    STUDENT_PROPOSE_IDEA = "Student_Propose_Idea"
    STUDENT_AGREE = "Student_Agree"
    STUDENT_DISAGREE = "Student_Disagree"

    # AI Agent activities
    BOT_FETCH = "Bot_FETCH"
    BOT_NO_FETCH = "Bot_NO_FETCH"
    BOT_RESPONSE = "Bot_Response"
    BOT_INTERVENTION = "Bot_Intervention"

    # System activities
    SYSTEM_INTERVENTION_TRIGGER = "System_Intervention_Trigger"
    SYSTEM_SUMMARY = "System_Summary"
    SYSTEM_QUALITY_CHECK = "System_Quality_Check"

    # Teacher/Instructor activities
    TEACHER_INTERVENTION = "Teacher_Intervention"
    TEACHER_FEEDBACK = "Teacher_Feedback"


class Lifecycle(str, Enum):
    """Standard XES lifecycle transitions."""

    START = "start"
    COMPLETE = "complete"
    SUSPEND = "suspend"
    RESUME = "resume"
    ABORT = "abort"


@dataclass
class EventLogEntry:
    """Represents a single event log entry for process mining."""

    case_id: str  # Group/Session ID
    activity: str  # Activity type
    timestamp: datetime  # When the event occurred
    resource: str  # User/Agent ID
    lifecycle: Lifecycle  # XES lifecycle state
    attributes: Optional[Dict[str, Any]] = None  # Additional attributes


class ProcessMiningLogger:
    """
    Logger for Educational Process Mining events.

    Records structured event logs for:
    - Visualizing learning workflows
    - Extracting orchestration patterns
    - Analyzing student-AI interactions
    - Supporting SSRL research analysis
    """

    # CSV header following XES/EPM standard with extended metadata
    CSV_HEADER = [
        "CaseID",  # Group/Session ID
        "Activity",  # Interaction type
        "Timestamp",  # ISO format
        "Resource",  # User/Agent ID
        "Lifecycle",  # XES lifecycle
        "CourseID",  # Course identifier
        "ChatRoomID",  # Chat room/space ID
        "Topic",  # Discussion topic
        "EngagementType",  # Cognitive/Behavioral/Emotional
        "LexicalVariety",  # SSRL metric (0-1)
        "IsHOT",  # Higher-Order Thinking flag
        "MessageLength",  # Character count
        "ExtraAttributes",  # JSON for additional data
    ]

    def __init__(self, log_dir: Optional[str] = None):
        """
        Initialize the process mining logger.

        Args:
            log_dir: Directory for log files. Defaults to data/event_logs/
        """
        self.log_dir = Path(log_dir) if log_dir else Path("data/event_logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Main event log file
        self.log_file = self.log_dir / "event_logs.csv"

        # Ensure header exists
        self._ensure_header()

        logger.info("process_mining_logger_initialized", log_file=str(self.log_file))

    def log_event(
        self,
        case_id: str,
        activity: str,
        resource: str,
        lifecycle: Lifecycle = Lifecycle.COMPLETE,
        course_id: Optional[str] = None,
        chat_room_id: Optional[str] = None,
        topic: Optional[str] = None,
        engagement_type: Optional[str] = None,
        lexical_variety: Optional[float] = None,
        is_hot: Optional[bool] = None,
        message_length: Optional[int] = None,
        extra_attributes: Optional[Dict[str, Any]] = None,
    ) -> EventLogEntry:
        """
        Log an event for process mining.

        Args:
            case_id: Group or Session identifier
            activity: Interaction type (from ActivityType or custom)
            resource: Actor (User ID or Agent ID)
            lifecycle: XES lifecycle state
            course_id: Course/Class identifier
            chat_room_id: Chat room/space identifier
            topic: Current discussion topic
            engagement_type: Cognitive/Behavioral/Emotional
            lexical_variety: SSRL metric (0-1)
            is_hot: Higher-Order Thinking detected
            message_length: Length of message
            extra_attributes: Additional custom attributes

        Returns:
            EventLogEntry recorded in CSV
        """
        timestamp = datetime.now()

        entry = EventLogEntry(
            case_id=case_id,
            activity=activity,
            timestamp=timestamp,
            resource=resource,
            lifecycle=lifecycle,
            attributes=extra_attributes,
        )

        # Write to CSV
        try:
            with open(self.log_file, mode="a", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(
                    [
                        case_id,
                        activity,
                        timestamp.isoformat(),
                        resource,
                        lifecycle.value,
                        course_id or "",
                        chat_room_id or "",
                        topic or "",
                        engagement_type or "",
                        f"{lexical_variety:.3f}" if lexical_variety is not None else "",
                        str(is_hot) if is_hot is not None else "",
                        str(message_length) if message_length is not None else "",
                        str(sanitize_sensitive_data(extra_attributes))
                        if extra_attributes
                        else "",
                    ]
                )

            logger.debug(
                "event_logged",
                case_id=case_id,
                activity=activity,
                resource=resource,
                course_id=course_id,
            )

        except Exception:
            logger.exception("event_logging_failed", case_id=case_id, activity=activity)

        return entry

    def log_student_message(
        self,
        group_id: str,
        user_id: str,
        message_length: int,
        course_id: Optional[str] = None,
        chat_room_id: Optional[str] = None,
        topic: Optional[str] = None,
        engagement_type: Optional[str] = None,
        lexical_variety: Optional[float] = None,
        is_hot: Optional[bool] = None,
    ) -> EventLogEntry:
        """Log a student message event with full context."""
        return self.log_event(
            case_id=group_id,
            activity=ActivityType.STUDENT_MESSAGE.value,
            resource=user_id,
            course_id=course_id,
            chat_room_id=chat_room_id,
            topic=topic,
            engagement_type=engagement_type,
            lexical_variety=lexical_variety,
            is_hot=is_hot,
            message_length=message_length,
        )

    def log_bot_response(
        self,
        group_id: str,
        action_taken: str,  # "FETCH" or "NO_FETCH"
        response_length: int,
        course_id: Optional[str] = None,
        chat_room_id: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> EventLogEntry:
        """Log a bot response event with action taken and context."""
        activity = (
            ActivityType.BOT_FETCH.value
            if action_taken == "FETCH"
            else ActivityType.BOT_NO_FETCH.value
        )

        return self.log_event(
            case_id=group_id,
            activity=activity,
            resource="AI_Agent",
            course_id=course_id,
            chat_room_id=chat_room_id,
            topic=topic,
            message_length=response_length,
            extra_attributes={"action": action_taken},
        )

    def log_intervention(
        self,
        group_id: str,
        intervention_type: str,
        trigger_reason: str,
        course_id: Optional[str] = None,
        chat_room_id: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> EventLogEntry:
        """Log a system intervention event with full context."""
        return self.log_event(
            case_id=group_id,
            activity=ActivityType.SYSTEM_INTERVENTION_TRIGGER.value,
            resource="Orchestrator",
            course_id=course_id,
            chat_room_id=chat_room_id,
            topic=topic,
            extra_attributes={
                "intervention_type": intervention_type,
                "trigger_reason": trigger_reason,
            },
        )

    def get_logs_for_case(self, case_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all log entries for a specific case (group).

        Args:
            case_id: The case/group ID to filter by

        Returns:
            List of log entries as dictionaries
        """
        entries = []

        try:
            with open(self.log_file, mode="r", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if row.get("CaseID") == case_id:
                        entries.append(dict(row))
        except FileNotFoundError:
            logger.warning("log_file_not_found", file=str(self.log_file))
        except Exception:
            logger.exception("log_read_failed")

        return entries

    def export_for_prom(self, output_file: Optional[str] = None) -> str:
        """
        Export logs in a format ready for ProM/Disco import.

        Args:
            output_file: Optional output file path

        Returns:
            Path to the exported file
        """
        output_path = output_file or str(self.log_dir / "export_prom.csv")

        # ProM requires specific column names
        prom_header = [
            "case:concept:name",
            "concept:name",
            "time:timestamp",
            "org:resource",
        ]

        try:
            with open(self.log_file, mode="r", encoding="utf-8") as infile:
                reader = csv.DictReader(infile)

                with open(
                    output_path, mode="w", newline="", encoding="utf-8"
                ) as outfile:
                    writer = csv.writer(outfile)
                    writer.writerow(prom_header)

                    for row in reader:
                        writer.writerow(
                            [
                                row.get("CaseID", ""),
                                row.get("Activity", ""),
                                row.get("Timestamp", ""),
                                row.get("Resource", ""),
                            ]
                        )

            logger.info("prom_export_complete", file=output_path)
            return output_path

        except Exception:
            logger.exception("prom_export_failed")
            raise

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about logged events."""
        stats = {
            "total_events": 0,
            "unique_cases": set(),
            "unique_resources": set(),
            "activity_counts": {},
            "hot_count": 0,
        }

        try:
            with open(self.log_file, mode="r", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    stats["total_events"] += 1
                    stats["unique_cases"].add(row.get("CaseID", ""))
                    stats["unique_resources"].add(row.get("Resource", ""))

                    activity = row.get("Activity", "unknown")
                    stats["activity_counts"][activity] = (
                        stats["activity_counts"].get(activity, 0) + 1
                    )

                    if row.get("IsHOT") == "True":
                        stats["hot_count"] += 1
        except FileNotFoundError:
            pass
        except Exception:
            logger.exception("stats_calculation_failed")

        # Convert sets to counts
        stats["unique_cases"] = len(stats["unique_cases"])
        stats["unique_resources"] = len(stats["unique_resources"])

        return stats

    def _ensure_header(self):
        """Ensure the log file has a header row."""
        if not self.log_file.exists():
            with open(self.log_file, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(self.CSV_HEADER)


# Singleton instance
_pm_logger: Optional[ProcessMiningLogger] = None


def get_process_mining_logger() -> ProcessMiningLogger:
    """Get or create the process mining logger singleton."""
    global _pm_logger
    if _pm_logger is None:
        _pm_logger = ProcessMiningLogger()
    return _pm_logger


def log_event_for_mining(
    case_id: str, activity: str, resource: str, lifecycle: str = "complete"
) -> EventLogEntry:
    """
    Convenience function for logging events (compatible with research spec).

    Args:
        case_id: Group/Session ID
        activity: Interaction Type
        resource: User/Actor ID
        lifecycle: XES lifecycle (default: complete)

    Returns:
        EventLogEntry that was recorded
    """
    pm_logger = get_process_mining_logger()
    return pm_logger.log_event(
        case_id=case_id,
        activity=activity,
        resource=resource,
        lifecycle=Lifecycle(lifecycle),
    )
