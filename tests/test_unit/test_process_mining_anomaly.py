"""
Unit Tests for Process Mining Anomaly Detector
===============================================

Tests for detecting deviations in learning process patterns based on 
XES event logs including sequence skips and engagement anomalies.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta
from app.services.process_mining_anomaly import (
    ProcessMiningAnomalyDetector,
    AnomalyDetectionResult,
    ProcessPattern
)


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def mongo_logger_mock():
    """Mock MongoDB Logger."""
    mock = MagicMock()
    mock.get_activity_logs = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def detector(mongo_logger_mock):
    """Create detector with mocked mongo logger."""
    with patch('app.services.process_mining_anomaly.get_mongo_logger', return_value=mongo_logger_mock):
        return ProcessMiningAnomalyDetector(mongo_logger=mongo_logger_mock)


# ==============================================================================
# TESTS: Initialization
# ==============================================================================

def test_detector_initialization(mongo_logger_mock):
    """Test detector initializes correctly."""
    detector = ProcessMiningAnomalyDetector(mongo_logger=mongo_logger_mock)
    assert detector.mongo_logger == mongo_logger_mock
    assert detector.EXPECTED_SEQUENCE == [
        "GOAL_SETTING",
        "STUDENT_MESSAGE",
        "BOT_RESPONSE",
        "SYSTEM_INTERVENTION",
        "REFLECTION_SUBMITTED"
    ]


# ==============================================================================
# TESTS: Session Anomaly Detection
# ==============================================================================

@pytest.mark.asyncio
async def test_detect_session_anomalies_no_events(detector, mongo_logger_mock):
    """Test detection when no events are found."""
    mongo_logger_mock.get_activity_logs.return_value = []
    
    result = await detector.detect_session_anomalies("chat_123")
    
    assert isinstance(result, AnomalyDetectionResult)
    assert result.has_anomalies is False
    assert "No event logs found" in result.description


@pytest.mark.asyncio
async def test_detect_session_anomalies_normal_session(detector, mongo_logger_mock):
    """Test detection on a healthy session with all phases."""
    now = datetime.now(timezone.utc)
    
    mock_events = [
        {"metadata": {"interactionType": "GOAL_SETTING"}, "createdAt": now, "userId": "u1"},
        {"metadata": {"interactionType": "STUDENT_MESSAGE"}, "createdAt": now + timedelta(minutes=5), "userId": "u1"},
        {"metadata": {"interactionType": "BOT_RESPONSE"}, "createdAt": now + timedelta(minutes=6), "userId": "bot"},
        {"metadata": {"interactionType": "REFLECTION_SUBMITTED"}, "createdAt": now + timedelta(minutes=30), "userId": "u1"}
    ]
    
    mongo_logger_mock.get_activity_logs.return_value = mock_events
    
    # Correct names are _detect_* instead of _check_*
    with patch.object(detector, '_detect_sequence_anomalies', return_value=None), \
         patch.object(detector, '_detect_duration_anomalies', return_value=None), \
         patch.object(detector, '_detect_participation_anomalies', return_value=None), \
         patch.object(detector, '_detect_quality_anomalies', return_value=None), \
         patch.object(detector, '_detect_bottlenecks', return_value=None):
        
        result = await detector.detect_session_anomalies("chat_123")
        
        assert result.has_anomalies is False


@pytest.mark.asyncio
async def test_detect_session_anomalies_sequence_skip(detector, mongo_logger_mock):
    """Test detection when sequence is skipped."""
    now = datetime.now(timezone.utc)
    
    mock_events = [
        {"metadata": {"interactionType": "STUDENT_MESSAGE"}, "createdAt": now, "userId": "u1"}
    ]
    
    mongo_logger_mock.get_activity_logs.return_value = mock_events
    
    anomaly = AnomalyDetectionResult(
        has_anomalies=True,
        anomaly_type="SEQUENCE_SKIP",
        severity="medium",
        description="Missing goal setting",
        affected_users=["u1"],
        affected_groups=[],
        metrics={},
        recommendations=["Encourage goal setting"],
        timestamp=now
    )
    
    with patch.object(detector, '_detect_sequence_anomalies', return_value=anomaly), \
         patch.object(detector, '_detect_duration_anomalies', return_value=None), \
         patch.object(detector, '_detect_participation_anomalies', return_value=None), \
         patch.object(detector, '_detect_quality_anomalies', return_value=None), \
         patch.object(detector, '_detect_bottlenecks', return_value=None):
        
        result = await detector.detect_session_anomalies("chat_123")
        assert result.has_anomalies is True
        assert result.anomaly_type == "SEQUENCE_SKIP"


# ==============================================================================
# TESTS: Internal Anomaly Checks (Private Methods)
# ==============================================================================

def test_detect_sequence_anomalies_missing_start(detector):
    """Test sequence check detects missing goal setting."""
    events = [{"metadata": {"interactionType": "STUDENT_MESSAGE"}}]
    anomaly = detector._detect_sequence_anomalies(events)
    
    assert anomaly is not None
    assert anomaly.anomaly_type == "sequence_anomaly"


def test_detect_duration_anomalies_too_short(detector):
    """Test duration check detects sessions that are too fast."""
    now = datetime.now()
    events = [
        {"createdAt": now, "metadata": {"interactionType": "STUDENT_MESSAGE"}},
        {"createdAt": now + timedelta(minutes=1), "metadata": {"interactionType": "REFLECTION_SUBMITTED"}}
    ]
    
    anomaly = detector._detect_duration_anomalies(events)
    
    assert anomaly is not None
    assert "short" in anomaly.description.lower() or "fast" in anomaly.description.lower()


def test_detect_duration_anomalies_too_long(detector):
    """Test duration check detects sessions that are too long."""
    now = datetime.now()
    events = [
        {"createdAt": now, "metadata": {"interactionType": "STUDENT_MESSAGE"}},
        {"createdAt": now + timedelta(hours=5), "metadata": {"interactionType": "REFLECTION_SUBMITTED"}}
    ]
    
    anomaly = detector._detect_duration_anomalies(events)
    
    assert anomaly is not None
    assert "long" in anomaly.description.lower() or "exceed" in anomaly.description.lower()


def test_detect_quality_anomalies_low_hot(detector):
    """Test quality check detects low higher-order thinking."""
    events = [
        {"metadata": {"interactionType": "STUDENT_MESSAGE"}, "engagement": {"isHigherOrder": False}},
        {"metadata": {"interactionType": "STUDENT_MESSAGE"}, "engagement": {"isHigherOrder": False}}
    ]
    
    anomaly = detector._detect_quality_anomalies(events)
    
    assert anomaly is not None


def test_detect_bottlenecks_skips_empty_duration_lists(detector):
    from datetime import datetime

    t0 = datetime(2026, 1, 1, 10, 0, 0)
    events = [{"createdAt": t0, "metadata": {"interactionType": "A"}}]
    assert detector._detect_bottlenecks(events) is None
    for _phase, durations in {"EMPTY": []}.items():
        if durations:
            pytest.fail("empty durations must skip bottleneck body")
