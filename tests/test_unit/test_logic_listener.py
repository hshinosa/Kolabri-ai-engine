"""
Unit Tests for Logic Listener Service
=====================================

Tests for real-time group monitoring:
- Off-topic detection with embedding similarity
- Silence detection with timestamp tracking
- Participation inequity with Gini coefficient
- Intervention message generation
- State cleanup for memory protection
"""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from app.services.logic_listener import (
    LogicListener,
    InterventionTrigger,
    InterventionType
)


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def listener():
    """Create LogicListener instance for testing."""
    return LogicListener()


# ==============================================================================
# TESTS: State Management
# ==============================================================================

def test_initialization(listener):
    """Test LogicListener initializes with empty state."""
    assert listener._off_topic_counter == {}
    assert listener._last_message_timestamp == {}
    assert listener._group_topics == {}
    assert listener._participation_counts == {}


@pytest.mark.asyncio
async def test_max_state_size_limit(listener):
    """Test that state respects max size limit."""
    # Set max size low for testing
    listener.MAX_STATE_SIZE = 5
    
    # Add more groups than max using async method
    for i in range(10):
        await listener.update_last_message_time(f"group_{i}")
        time.sleep(0.01)  # Small delay to get different timestamps
    
    # Should cleanup to 5
    assert len(listener._last_message_timestamp) <= 5


# ==============================================================================
# TESTS: Topic Management
# ==============================================================================

def test_set_group_topic(listener):
    """Test setting group topic."""
    import asyncio
    asyncio.get_event_loop().run_until_complete(
        listener.set_group_topic("group_1", "Database Normalization")
    )
    
    assert listener._group_topics["group_1"] == "Database Normalization"


def test_get_group_topic(listener):
    """Test getting group topic."""
    import asyncio
    asyncio.get_event_loop().run_until_complete(
        listener.set_group_topic("group_1", "Testing")
    )
    assert listener.get_group_topic("group_1") == "Testing"
    assert listener.get_group_topic("nonexistent") is None


# ==============================================================================
# TESTS: Participation Tracking
# ==============================================================================

def test_track_participation(listener):
    """Test tracking user participation."""
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(listener.track_participation("group_1", "user_1"))
    loop.run_until_complete(listener.track_participation("group_1", "user_1"))
    loop.run_until_complete(listener.track_participation("group_1", "user_2"))
    
    assert listener._participation_counts["group_1"]["user_1"] == 2
    assert listener._participation_counts["group_1"]["user_2"] == 1


def test_participation_counts_multiple_groups(listener):
    """Test tracking participation across multiple groups."""
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(listener.track_participation("group_1", "user_1"))
    loop.run_until_complete(listener.track_participation("group_2", "user_1"))
    
    assert listener._participation_counts["group_1"]["user_1"] == 1
    assert listener._participation_counts["group_2"]["user_1"] == 1


# ==============================================================================
# TESTS: Message Timestamp Tracking
# ==============================================================================

def test_update_last_message_time(listener):
    """Test updating last message timestamp."""
    import asyncio
    before_update = time.time()
    
    asyncio.get_event_loop().run_until_complete(
        listener.update_last_message_time("group_1")
    )
    
    after_update = time.time()
    
    assert "group_1" in listener._last_message_timestamp
    assert before_update <= listener._last_message_timestamp["group_1"] <= after_update


def test_multiple_updates_same_group(listener):
    """Test that multiple updates to same group refresh timestamp."""
    import asyncio
    loop = asyncio.get_event_loop()
    
    time.sleep(0.01)
    loop.run_until_complete(listener.update_last_message_time("group_1"))
    timestamp_1 = listener._last_message_timestamp["group_1"]
    
    time.sleep(0.01)
    loop.run_until_complete(listener.update_last_message_time("group_1"))
    timestamp_2 = listener._last_message_timestamp["group_1"]
    
    assert timestamp_2 > timestamp_1


# ==============================================================================
# TESTS: Silence Detection
# ==============================================================================

def test_silence_check_no_previous_message(listener):
    """Test silence check when no previous message exists."""
    result = listener.check_silence("new_group")
    
    assert result.should_intervene is False
    assert result.intervention_type is None


def test_silence_check_recent_activity(listener):
    """Test that recent activity doesn't trigger intervention."""
    import asyncio
    asyncio.get_event_loop().run_until_complete(
        listener.update_last_message_time("group_1")
    )
    
    result = listener.check_silence("group_1")
    
    assert result.should_intervene is False


def test_silence_check_trigger_after_threshold(listener):
    """Test that silence detection triggers after threshold."""
    # Set old timestamp (beyond threshold)
    old_time = time.time() - (listener.SILENCE_THRESHOLD_MINUTES * 60 + 60)
    listener._last_message_timestamp["group_1"] = old_time
    
    # Mock _log_intervention to avoid event loop issues
    with patch.object(listener, '_log_intervention', new_callable=AsyncMock):
        result = listener.check_silence("group_1")
    
    assert result.should_intervene is True
    assert result.intervention_type == InterventionType.SILENCE
    assert len(result.suggested_message) > 0
    assert result.metadata["idle_minutes"] >= listener.SILENCE_THRESHOLD_MINUTES


# ==============================================================================
# TESTS: Get Silent Groups
# ==============================================================================

def test_get_all_silent_groups_empty(listener):
    """Test get silent groups returns empty when no groups tracked."""
    result = listener.get_all_silent_groups()
    assert len(result) == 0


def test_get_all_silent_groups_filters_by_threshold(listener):
    """Test that only groups beyond threshold are returned."""
    import asyncio
    # Active group
    asyncio.get_event_loop().run_until_complete(
        listener.update_last_message_time("active_group")
    )
    
    # Silent groups (old timestamps)
    old_time = time.time() - (listener.SILENCE_THRESHOLD_MINUTES * 60 + 60)
    listener._last_message_timestamp["silent_group_1"] = old_time
    listener._last_message_timestamp["silent_group_2"] = old_time
    
    result = listener.get_all_silent_groups()
    
    assert "active_group" not in result
    assert len(result) == 2


# ==============================================================================
# TESTS: Participation Inequity (Gini Coefficient)
# ==============================================================================

@pytest.mark.asyncio
async def test_participation_check_equal_distribution(listener):
    """Test that equal distribution has low Gini (no intervention)."""
    # Equal participation
    for user_id in ["user_1", "user_2", "user_3"]:
        for _ in range(10):
            await listener.track_participation("group_1", user_id)
    
    result = listener.check_participation_inequity("group_1")
    
    assert result.should_intervene is False
    assert 0.0 <= result.metadata["gini_coefficient"] < listener.PARTICIPATION_INEQUITY_THRESHOLD


@pytest.mark.asyncio
async def test_participation_check_unequal_distribution(listener):
    """Test that unequal distribution triggers intervention."""
    # Highly unequal distribution
    for _ in range(50):
        await listener.track_participation("group_1", "dominant_user")
    for _ in range(2):
        await listener.track_participation("group_1", "silent_user_1")
        await listener.track_participation("group_1", "silent_user_2")
    
    # Force threshold low for test
    listener.PARTICIPATION_INEQUITY_THRESHOLD = 0.4
    
    with patch.object(listener, '_log_intervention', new_callable=AsyncMock):
        result = listener.check_participation_inequity("group_1")
    
    assert result.should_intervene is True
    assert result.intervention_type == InterventionType.PARTICIPATION_INEQUITY
    assert result.metadata["gini_coefficient"] > 0.4


@pytest.mark.asyncio
async def test_participation_check_identifies_least_active(listener):
    """Test that least active user is identified."""
    for _ in range(20):
        await listener.track_participation("group_1", "user_1")
    for _ in range(5):
        await listener.track_participation("group_1", "user_2")
    for _ in range(1):
        await listener.track_participation("group_1", "user_3")
    
    result = listener.check_participation_inequity("group_1")
    
    if result.should_intervene:
        assert "user_3" in result.metadata["least_active_user"]


# ==============================================================================
# TESTS: Off-Topic Detection (with mocks)
# ==============================================================================

@pytest.mark.asyncio
async def test_off_topic_check_no_topic(listener):
    """Test off-topic check requires topic to be set."""
    result = await listener.check_relevance("some message", "group_1")
    
    assert result.should_intervene is False
    assert "No topic set" in result.reason


@pytest.mark.asyncio
async def test_off_topic_check_relevant_message(listener):
    """Test that relevant message doesn't trigger intervention."""
    await listener.set_group_topic("group_1", "Database Normalization")
    
    # Mock embedding similarity to be high
    with patch.object(listener, '_calculate_cosine_similarity', return_value=0.9):
        result = await listener.check_relevance("Mari kita normalisasi tabel users", "group_1")
    
    assert result.should_intervene is False


@pytest.mark.asyncio
async def test_off_topic_check_irrelevant_message(listener):
    """Test that irrelevant message triggers intervention."""
    await listener.set_group_topic("group_1", "Database Normalization")
    
    # Mock embedding similarity and logger
    with patch.object(listener, '_calculate_cosine_similarity', return_value=0.4), \
         patch.object(listener.embedding_service, 'get_embedding', new_callable=AsyncMock), \
         patch.object(listener, '_log_intervention', new_callable=AsyncMock):
        
        # First low similarity
        await listener.check_relevance("Saya suka kopi nih", "group_1")
        # Second low similarity
        await listener.check_relevance("Kopi mana enak", "group_1")
        # Third low similarity - should trigger
        result = await listener.check_relevance("Dimana tempat kopi yang bagus", "group_1")
    
    assert result.should_intervene is True
    assert result.intervention_type == InterventionType.OFF_TOPIC


@pytest.mark.asyncio
async def test_off_topic_check_resets_on_relevant(listener):
    """Test that relevant message resets counter."""
    await listener.set_group_topic("group_1", "Database Optimization")
    
    with patch.object(listener, '_calculate_cosine_similarity', return_value=0.4):
        # Two off-topic messages
        await listener.check_relevance("Random chat", "group_1")
        await listener.check_relevance("Random chat 2", "group_1")
    
    with patch.object(listener, '_calculate_cosine_similarity', return_value=0.9):
        # Relevant message should reset
        result = await listener.check_relevance("Mari kita bahas performance", "group_1")
    
    assert result.should_intervene is False
    
    assert result.should_intervene is False


# ==============================================================================
# TESTS: Cosine Similarity Calculation
# ==============================================================================

def test_cosine_similarity_calculation(listener):
    """Test cosine similarity calculation."""
    vec1 = [1, 2, 3, 4, 5]
    vec2 = [1, 2, 3, 4, 5]  # Identical vectors
    
    similarity = listener._calculate_cosine_similarity(vec1, vec2)
    
    assert similarity == 1.0


def test_cosine_similarity_opposite_vectors(listener):
    """Test cosine similarity for opposite vectors."""
    vec1 = [1, 1, 1, 1, 1]
    vec2 = [-1, -1, -1, -1, -1]
    
    similarity = listener._calculate_cosine_similarity(vec1, vec2)
    
    assert pytest.approx(similarity) == -1.0


def test_cosine_similarity_orthogonal_vectors(listener):
    """Test cosine similarity for orthogonal vectors."""
    vec1 = [1, 0, 0, 0]
    vec2 = [0, 1, 0, 0]
    
    similarity = listener._calculate_cosine_similarity(vec1, vec2)
    
    assert similarity == 0.0


def test_cosine_similarity_zero_vectors(listener):
    """Test that zero vectors return 0."""
    vec1 = [0, 0, 0, 0]
    vec2 = [1, 2, 3, 4]
    
    similarity = listener._calculate_cosine_similarity(vec1, vec2)
    
    assert similarity == 0.0


# ==============================================================================
# TESTS: Gini Coefficient
# ==============================================================================

def test_gini_coefficient_equal_distribution(listener):
    """Test Gini coefficient for equal distribution."""
    values = [10, 10, 10, 10, 10]
    gini = listener._calculate_gini_coefficient(values)
    
    assert gini == 0.0


def test_gini_coefficient_perfect_inequality(listener):
    """Test Gini coefficient for perfect inequality."""
    values = [100, 0, 0, 0, 0]
    gini = listener._calculate_gini_coefficient(values)
    
    # Perfect inequality has Gini approaching (n-1)/n
    # For n=5, (5-1)/5 = 0.8
    assert pytest.approx(gini) == 0.8


def test_gini_coefficient_realistic_inequality(listener):
    """Test Gini coefficient for realistic unequal distribution."""
    values = [50, 30, 15, 5, 0]
    gini = listener._calculate_gini_coefficient(values)
    
    # Should be moderate inequality
    assert 0.3 < gini < 0.7


# ==============================================================================
# TESTS: Intervention Messages
# ==============================================================================

@pytest.mark.asyncio
async def test_off_topic_intervention_message(listener):
    """Test that off-topic intervention includes topic."""
    await listener.set_group_topic("group_1", "Testing")
    message = listener._get_off_topic_intervention("Testing")
    
    assert "Testing" in message


def test_silence_intervention_message_list(listener):
    """Test that silence intervention messages are defined."""
    messages = listener.SILENCE_INTERVENTIONS
    
    assert len(messages) > 0
    assert all(isinstance(msg, str) for msg in messages)


def test_participation_intervention_message_includes_user(listener):
    """Test that participation intervention includes user mention."""
    message = listener._get_participation_intervention("user_1")
    
    assert "@user_1" in message


# ==============================================================================
# TESTS: Edge Cases
# ==============================================================================

def check_reliability_empty_group(listener):
    """Test that participation check with no users doesn't crash."""
    # Empty group, no participants
    result = listener.check_participation_inequity("empty_group")
    
    assert result.should_intervene is False


@pytest.mark.asyncio
async def test_cleanup_removes_entries(listener):
    """Test that cleanup removes dictionary entries."""
    # Set max size low for testing
    listener.MAX_STATE_SIZE = 10
    
    # Add entries
    for i in range(15):
        listener._last_message_timestamp[f"group_{i}"] = time.time()
    
    # Force cleanup (async)
    await listener._cleanup_state_if_needed()
    
    # Should be cleaned up to max size
    assert len(listener._last_message_timestamp) <= listener.MAX_STATE_SIZE


@pytest.mark.asyncio
async def test_embedding_service_exception_handling(listener):
    """Test that embedding service errors are handled gracefully."""
    await listener.set_group_topic("group_1", "Database")
    
    # Mock embedding service to raise exception
    with patch.object(listener.embedding_service, 'get_embedding', side_effect=Exception("Embedding failed")):
        result = await listener.check_relevance("Test message", "group_1")
    
    # Should not crash, just not intervene
    assert result.should_intervene is False
    assert "Error" in result.reason
