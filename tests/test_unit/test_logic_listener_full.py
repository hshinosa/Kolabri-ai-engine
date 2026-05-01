"""
Tests for Logic Listener Service - Full Coverage
"""
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.logic_listener import (
    LogicListener,
    InterventionType,
    InterventionTrigger,
    get_logic_listener,
)


class TestInterventionType:
    """Test InterventionType enum."""
    
    def test_values(self):
        """Test enum values."""
        assert InterventionType.OFF_TOPIC.value == "off_topic"
        assert InterventionType.SILENCE.value == "silence"
        assert InterventionType.PARTICIPATION_INEQUITY.value == "participation_inequity"


class TestInterventionTrigger:
    """Test InterventionTrigger dataclass."""
    
    def test_to_dict(self):
        """Test to_dict conversion."""
        trigger = InterventionTrigger(
            should_intervene=True,
            intervention_type=InterventionType.OFF_TOPIC,
            reason="Test reason",
            suggested_message="Test message",
            metadata={"key": "value"}
        )
        
        result = trigger.to_dict()
        
        assert result["should_intervene"] is True
        assert result["intervention_type"] == "off_topic"
        assert result["reason"] == "Test reason"
        assert result["suggested_message"] == "Test message"
        assert result["metadata"] == {"key": "value"}


class TestLogicListener:
    """Test LogicListener class."""
    
    @pytest.fixture
    def mock_embedding_service(self):
        """Create mock embedding service."""
        mock = MagicMock()
        mock.get_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])
        return mock
    
    @pytest.fixture
    def mock_mongo_logger(self):
        """Create mock MongoDB logger."""
        mock = MagicMock()
        mock.log_intervention = AsyncMock()
        return mock
    
    @pytest.fixture
    def logic_listener(self, mock_embedding_service, mock_mongo_logger):
        """Create logic listener with mocks."""
        with patch('app.services.logic_listener.get_embedding_service', return_value=mock_embedding_service):
            with patch('app.services.logic_listener.get_mongo_logger', return_value=mock_mongo_logger):
                return LogicListener()
    
    def test_init(self, logic_listener):
        """Test initialization."""
        assert logic_listener._off_topic_counter == {}
        assert logic_listener._last_message_timestamp == {}
        assert logic_listener._group_topics == {}
        assert logic_listener._participation_counts == {}
    
    @pytest.mark.asyncio
    async def test_set_group_topic(self, logic_listener):
        """Test set_group_topic method."""
        await logic_listener.set_group_topic("group1", "Machine Learning")
        
        assert logic_listener._group_topics["group1"] == "Machine Learning"
    
    @pytest.mark.asyncio
    async def test_update_last_message_time(self, logic_listener):
        """Test update_last_message_time method."""
        await logic_listener.update_last_message_time("group1")
        
        assert "group1" in logic_listener._last_message_timestamp
    
    @pytest.mark.asyncio
    async def test_track_participation(self, logic_listener):
        """Test track_participation method."""
        await logic_listener.track_participation("group1", "user1")
        await logic_listener.track_participation("group1", "user1")
        
        assert logic_listener._participation_counts["group1"]["user1"] == 2
    
    @pytest.mark.asyncio
    async def test_track_participation_new_user(self, logic_listener):
        """Test track_participation with new user."""
        await logic_listener.track_participation("group1", "user1")
        
        assert "group1" in logic_listener._participation_counts
        assert "user1" in logic_listener._participation_counts["group1"]
    
    @pytest.mark.asyncio
    async def test_check_relevance_no_topic(self, logic_listener):
        """Test check_relevance when no topic set."""
        result = await logic_listener.check_relevance("Test message", "group1")
        
        assert result.should_intervene is False
        assert result.intervention_type is None
    
    @pytest.mark.asyncio
    async def test_check_relevance_on_topic(self, logic_listener, mock_embedding_service):
        """Test check_relevance with on-topic message."""
        logic_listener._group_topics["group1"] = "Machine Learning"
        mock_embedding_service.get_embedding.return_value = [0.9, 0.1, 0.0]
        
        result = await logic_listener.check_relevance("Neural networks are great", "group1")
        
        assert result.should_intervene is False
    
    @pytest.mark.asyncio
    async def test_check_relevance_off_topic(self, logic_listener, mock_embedding_service):
        """Test check_relevance with off-topic message."""
        logic_listener._group_topics["group1"] = "Machine Learning"
        
        # Need 3 consecutive off-topic messages with similarity < 0.6
        # Use orthogonal vectors to get ~0 similarity
        for i in range(3):
            mock_embedding_service.get_embedding.side_effect = [
                [1.0, 0.0, 0.0],  # message embedding (orthogonal to topic)
                [0.0, 1.0, 0.0],  # topic embedding (orthogonal to message)
            ]
            result = await logic_listener.check_relevance(f"Off topic {i}", "group1")
        
        assert result.should_intervene is True
        assert result.intervention_type == InterventionType.OFF_TOPIC
    
    @pytest.mark.asyncio
    async def test_check_relevance_resets_counter(self, logic_listener, mock_embedding_service):
        """Test check_relevance resets counter on relevant message."""
        logic_listener._group_topics["group1"] = "ML"
        logic_listener._off_topic_counter["group1"] = 2
        
        # Send relevant message
        mock_embedding_service.get_embedding.return_value = [0.9, 0.9, 0.9]
        result = await logic_listener.check_relevance("Machine learning", "group1")
        
        assert result.should_intervene is False
        assert logic_listener._off_topic_counter.get("group1", 0) == 0
    
    @pytest.mark.asyncio
    async def test_check_relevance_exception(self, logic_listener):
        """Test check_relevance with exception."""
        logic_listener._group_topics["group1"] = "Test"
        logic_listener.embedding_service.get_embedding = AsyncMock(side_effect=Exception("Error"))
        
        result = await logic_listener.check_relevance("Test", "group1")
        
        assert result.should_intervene is False
    
    def test_check_silence_no_timestamp(self, logic_listener):
        """Test check_silence with no timestamp."""
        result = logic_listener.check_silence("group1")
        
        assert result.should_intervene is False
    
    def test_check_silence_not_silent(self, logic_listener):
        """Test check_silence when not silent."""
        logic_listener._last_message_timestamp["group1"] = time.time()
        
        result = logic_listener.check_silence("group1")
        
        assert result.should_intervene is False
    
    def test_check_silence_detected(self, logic_listener):
        """Test check_silence when silence detected."""
        # Set timestamp to 15 minutes ago (threshold is 10)
        logic_listener._last_message_timestamp["group1"] = time.time() - (15 * 60)
        
        result = logic_listener.check_silence("group1")
        
        assert result.should_intervene is True
        assert result.intervention_type == InterventionType.SILENCE
    
    def test_check_participation_inequity_insufficient(self, logic_listener):
        """Test check_participation_inequity with insufficient participants."""
        logic_listener._participation_counts["group1"] = {"user1": 10}
        
        result = logic_listener.check_participation_inequity("group1")
        
        assert result.should_intervene is False
    
    def test_check_participation_inequity_equitable(self, logic_listener):
        """Test check_participation_inequity with equitable participation."""
        logic_listener._participation_counts["group1"] = {"user1": 10, "user2": 10}
        
        result = logic_listener.check_participation_inequity("group1")
        
        assert result.should_intervene is False
    
    def test_check_participation_inequity_detected(self, logic_listener):
        """Test check_participation_inequity when inequity detected."""
        # Create high inequality (Gini > 0.6 threshold)
        logic_listener._participation_counts["group1"] = {"user1": 100, "user2": 1, "user3": 1}
        
        result = logic_listener.check_participation_inequity("group1")
        
        assert result.should_intervene is True
        assert result.intervention_type == InterventionType.PARTICIPATION_INEQUITY
        assert "user2" in result.suggested_message or "user3" in result.suggested_message
    
    def test_check_participation_inequity_empty(self, logic_listener):
        """Test check_participation_inequity with no participation."""
        logic_listener._participation_counts["group1"] = {}
        
        result = logic_listener.check_participation_inequity("group1")
        
        assert result.should_intervene is False
    
    def test_get_all_silent_groups(self, logic_listener):
        """Test get_all_silent_groups method."""
        # Set one group as silent
        logic_listener._last_message_timestamp["group1"] = time.time() - (15 * 60)
        logic_listener._last_message_timestamp["group2"] = time.time()
        
        silent_groups = logic_listener.get_all_silent_groups()
        
        assert "group1" in silent_groups
        assert "group2" not in silent_groups
    
    def test_get_group_topic(self, logic_listener):
        """Test get_group_topic method."""
        logic_listener._group_topics["group1"] = "Machine Learning"
        
        result = logic_listener.get_group_topic("group1")
        
        assert result == "Machine Learning"
    
    def test_get_group_topic_not_found(self, logic_listener):
        """Test get_group_topic for unknown group."""
        result = logic_listener.get_group_topic("unknown")
        
        assert result is None
    
    def test_calculate_cosine_similarity(self, logic_listener):
        """Test _calculate_cosine_similarity method."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        
        result = logic_listener._calculate_cosine_similarity(vec1, vec2)
        
        assert result == 1.0
    
    def test_calculate_cosine_similarity_orthogonal(self, logic_listener):
        """Test _calculate_cosine_similarity with orthogonal vectors."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        
        result = logic_listener._calculate_cosine_similarity(vec1, vec2)
        
        assert result == 0.0
    
    def test_calculate_cosine_similarity_zero_norm(self, logic_listener):
        """Test _calculate_cosine_similarity with zero norm."""
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [1.0, 0.0, 0.0]
        
        result = logic_listener._calculate_cosine_similarity(vec1, vec2)
        
        assert result == 0.0
    
    def test_calculate_gini_coefficient(self, logic_listener):
        """Test _calculate_gini_coefficient method."""
        values = [10, 10, 10, 10]  # Perfect equality
        
        result = logic_listener._calculate_gini_coefficient(values)
        
        assert result == 0.0
    
    def test_calculate_gini_coefficient_inequality(self, logic_listener):
        """Test _calculate_gini_coefficient with inequality."""
        values = [100, 1, 1, 1]  # High inequality
        
        result = logic_listener._calculate_gini_coefficient(values)
        
        assert result > 0.5
    
    def test_calculate_gini_coefficient_empty(self, logic_listener):
        """Test _calculate_gini_coefficient with empty list."""
        result = logic_listener._calculate_gini_coefficient([])
        
        assert result == 0.0
    
    def test_calculate_gini_coefficient_zero_sum(self, logic_listener):
        """Test _calculate_gini_coefficient with zero sum."""
        result = logic_listener._calculate_gini_coefficient([0, 0, 0])
        
        assert result == 0.0
    
    def test_get_off_topic_intervention(self, logic_listener):
        """Test _get_off_topic_intervention method."""
        result = logic_listener._get_off_topic_intervention("Machine Learning")
        
        assert "Machine Learning" in result
        assert len(result) > 0
    
    def test_get_silence_intervention(self, logic_listener):
        """Test _get_silence_intervention method."""
        result = logic_listener._get_silence_intervention()
        
        assert len(result) > 0
    
    def test_get_participation_intervention(self, logic_listener):
        """Test _get_participation_intervention method."""
        result = logic_listener._get_participation_intervention("user1")
        
        assert "user1" in result
        assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_log_intervention(self, logic_listener, mock_mongo_logger):
        """Test _log_intervention method."""
        await logic_listener._log_intervention(
            group_id="group1",
            intervention_type=InterventionType.OFF_TOPIC,
            reason="Test reason",
            metadata={"key": "value"}
        )
        
        mock_mongo_logger.log_intervention.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_log_intervention_exception(self, logic_listener):
        """Test _log_intervention with exception."""
        logic_listener.mongo_logger.log_intervention = AsyncMock(side_effect=Exception("Error"))
        
        # Should not raise
        await logic_listener._log_intervention(
            group_id="group1",
            intervention_type=InterventionType.OFF_TOPIC,
            reason="Test",
            metadata={}
        )
    
    @pytest.mark.asyncio
    async def test_cleanup_state_if_needed(self, logic_listener):
        """Test _cleanup_state_if_needed method."""
        # Fill up state beyond MAX_STATE_SIZE
        for i in range(logic_listener.MAX_STATE_SIZE + 50):
            logic_listener._last_message_timestamp[f"group{i}"] = time.time() - (i * 60)
            logic_listener._off_topic_counter[f"group{i}"] = i
            logic_listener._group_topics[f"group{i}"] = f"Topic {i}"
            logic_listener._participation_counts[f"group{i}"] = {"user1": i}
        
        await logic_listener._cleanup_state_if_needed()
        
        # Should have cleaned up 100 oldest entries
        assert len(logic_listener._last_message_timestamp) <= logic_listener.MAX_STATE_SIZE


class TestGetLogicListener:
    """Test get_logic_listener singleton."""
    
    def test_singleton(self):
        """Test get_logic_listener returns singleton."""
        from app.services import logic_listener
        logic_listener._logic_listener = None
        
        with patch('app.services.logic_listener.get_embedding_service') as mock_emb:
            mock_emb.return_value = MagicMock()
            with patch('app.services.logic_listener.get_mongo_logger') as mock_mongo:
                mock_mongo.return_value = MagicMock()
                
                listener1 = get_logic_listener()
                listener2 = get_logic_listener()
                
                assert listener1 is listener2
    
    def test_initialization(self):
        """Test get_logic_listener initializes correctly."""
        from app.services import logic_listener
        logic_listener._logic_listener = None
        
        with patch('app.services.logic_listener.get_embedding_service') as mock_emb:
            mock_emb.return_value = MagicMock()
            with patch('app.services.logic_listener.get_mongo_logger') as mock_mongo:
                mock_mongo.return_value = MagicMock()
                
                listener = get_logic_listener()
                
                assert listener is not None
                assert isinstance(listener, LogicListener)
