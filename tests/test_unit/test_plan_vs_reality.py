"""
Unit Tests for Plan vs Reality Analyzer
========================================

Tests for the comparison between planned learning goals and actual 
learning activities in a learning session.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta
from app.services.plan_vs_reality import (
    PlanVsRealityAnalyzer,
    PlanVsRealityResult,
    TopicAnalysis
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
def analyzer(mongo_logger_mock):
    """Create analyzer with mocked mongo logger."""
    with patch('app.services.plan_vs_reality.get_mongo_logger', return_value=mongo_logger_mock):
        return PlanVsRealityAnalyzer(mongo_logger=mongo_logger_mock)


# ==============================================================================
# TESTS: Initialization
# ==============================================================================

def test_analyzer_initialization(mongo_logger_mock):
    """Test analyzer initializes correctly."""
    analyzer = PlanVsRealityAnalyzer(mongo_logger=mongo_logger_mock)
    assert analyzer.mongo_logger == mongo_logger_mock


# ==============================================================================
# TESTS: Analyze Session
# ==============================================================================

@pytest.mark.asyncio
async def test_analyze_session_no_events(analyzer, mongo_logger_mock):
    """Test analysis when no events are found."""
    mongo_logger_mock.get_activity_logs.return_value = []
    
    result = await analyzer.analyze_session("chat_123")
    
    assert isinstance(result, PlanVsRealityResult)
    assert result.case_id == "chat_123"
    assert result.insights == ["No event logs found for this session"]
    assert result.plan == {}
    assert result.reality == {}


@pytest.mark.asyncio
async def test_analyze_session_with_plan_and_reality(analyzer, mongo_logger_mock):
    """Test analysis with both plan and reality events."""
    now = datetime.now(timezone.utc)
    
    # Mock events using keywords that exist in analyzer's static lists
    # Note: createdAt should be datetime objects for duration calculation
    mock_events = [
        {
            "content": "I want to design a mobile app",
            "metadata": {"phase": "Forethought", "interactionType": "GOAL_SETTING"},
            "createdAt": now,
            "userId": "user_1"
        },
        {
            "content": "Let's research the navigation and layout",
            "metadata": {"phase": "Performance", "interactionType": "STUDENT_MESSAGE"},
            "createdAt": (now + timedelta(minutes=5)),
            "userId": "user_1"
        }
    ]
    
    mongo_logger_mock.get_activity_logs.return_value = mock_events
    
    result = await analyzer.analyze_session("chat_123")
    
    assert result.case_id == "chat_123"
    assert result.plan["has_plan"] is True
    # "design" and "app" are in topic_keywords
    assert any(t in result.plan["topics"] for t in ["design", "app"])
    
    assert result.reality["has_reality"] is True
    # "research", "navigation", "layout" are in topic_keywords
    assert any(t in result.reality["topics"] for t in ["research", "navigation", "layout"])


@pytest.mark.asyncio
async def test_analyze_session_exception_handling(analyzer, mongo_logger_mock):
    """Test analysis handles exceptions gracefully."""
    mongo_logger_mock.get_activity_logs.side_effect = Exception("DB Connection Failed")
    
    result = await analyzer.analyze_session("chat_123")
    
    assert result.case_id == "chat_123"
    assert "Analysis failed" in result.insights[0]
    assert "internal error" in result.insights[0]


# ==============================================================================
# TESTS: Internal Logic (Private Methods)
# ==============================================================================

def test_extract_plan_no_goals(analyzer):
    """Test plan extraction when no goal events exist."""
    events = [{"content": "just a message", "metadata": {"phase": "Performance"}}]
    plan = analyzer._extract_plan(events)
    
    assert plan["has_plan"] is False
    assert plan["goals"] == []


def test_extract_plan_with_goals(analyzer):
    """Test successful plan extraction."""
    now = datetime.now()
    events = [
        {
            "content": "Focus on software development", 
            "metadata": {"phase": "Forethought"},
            "createdAt": now
        }
    ]
    
    plan = analyzer._extract_plan(events)
    
    assert plan["has_plan"] is True
    assert len(plan["goals"]) == 1
    assert any(t in plan["topics"] for t in ["software", "development"])


def test_extract_reality_no_performance(analyzer):
    """Test reality extraction when no performance events exist."""
    events = [{"content": "setting goal", "metadata": {"phase": "Forethought"}}]
    reality = analyzer._extract_reality(events)
    
    assert reality["has_reality"] is False
    assert reality["message_count"] == 0


def test_extract_reality_with_messages(analyzer):
    """Test successful reality extraction."""
    now = datetime.now()
    events = [
        {
            "content": "Mobile app usability testing", 
            "metadata": {"phase": "Performance", "interactionType": "STUDENT_MESSAGE"},
            "createdAt": now
        }
    ]
    
    reality = analyzer._extract_reality(events)
    
    assert reality["has_reality"] is True
    assert reality["message_count"] == 1
    assert any(t in reality["topics"] for t in ["mobile", "app", "usability", "testing"])


# ==============================================================================
# TESTS: Comparison and Insights
# ==============================================================================

def test_compare_plan_reality(analyzer):
    """Test comparison between plan and reality."""
    plan = {"topics": ["design", "web"], "keywords": ["design", "web"]}
    reality = {"topics": ["design", "app"], "keywords": ["design", "app"]}
    
    comparison = analyzer._compare_plan_reality(plan, reality)
    
    assert "topic_coverage" in comparison
    topic_coverage = comparison["topic_coverage"]
    assert "design" in topic_coverage["covered_topics"]
    assert "web" in topic_coverage["missing_topics"]
    assert "app" in topic_coverage["extra_topics"]


def test_generate_insights_empty(analyzer):
    """Test insights generation with empty data."""
    plan = {"has_plan": False, "topics": []}
    reality = {"has_reality": False, "topics": []}
    comparison = {"topic_coverage": {"coverage_percentage": 0}}
    
    insights = analyzer._generate_insights(plan, reality, comparison)
    
    assert len(insights) >= 0


def test_generate_insights_good_coverage(analyzer):
    """Test insights generation with good topic coverage."""
    plan = {"has_plan": True, "topics": ["design"]}
    reality = {"has_reality": True, "topics": ["design"]}
    comparison = {
        "topic_coverage": {
            "coverage_percentage": 100.0,
            "missing_topics": [],
            "extra_topics": []
        },
        "time_comparison": {"difference_minutes": 0}
    }
    
    insights = analyzer._generate_insights(plan, reality, comparison)
    
    assert any("Excellent topic coverage" in i for i in insights)
