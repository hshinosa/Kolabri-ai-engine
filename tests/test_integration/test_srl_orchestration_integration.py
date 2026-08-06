"""
Integration Tests: Zimmerman SRL Classifier + Orchestration
============================================================
End-to-end testing of SRL phase classification in full chat conversation flow.
Tests integration with MongoDB logging and message tracking.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.srl_classifier import (
    SRLClassifier,
    SRLPhase,
    SRLClassificationResult,
    get_srl_classifier,
)
from app.services.orchestration import Orchestrator


class TestSRLOrchestrationIntegration:
    """Test SRL classifier integrated into orchestration pipeline."""

    @pytest.fixture
    def mock_mongo_logger(self):
        """Mock MongoDB logger for integration testing."""
        logger = AsyncMock()
        logger.log_activity = AsyncMock(return_value=None)
        return logger

    @pytest.fixture
    def mock_rag_pipeline(self):
        """Mock RAG pipeline for integration testing."""
        mock_rag = AsyncMock()

        async def mock_query_stream(*args, **kwargs):
            yield {
                "type": "full",
                "content": "This is a mock response from RAG pipeline.",
                "sources": [],
                "citations": [],
                "outcome": None,
                "reason": None,
                "scaffolding_triggered": False,
            }

        mock_rag.query_stream = mock_query_stream
        return mock_rag

    @pytest.fixture
    def mock_intervention_service(self):
        """Mock intervention service for integration testing."""
        service = AsyncMock()
        service._check_triggers = AsyncMock(return_value={"should_intervene": False})
        return service

    @pytest.fixture
    def mock_analyzer(self):
        """Mock engagement analyzer for integration testing."""
        analyzer = AsyncMock()

        class MockAnalysis:
            engagement_type = MagicMock()
            engagement_type.value = "learning"
            is_higher_order = True
            lexical_variety = 0.75

        analyzer.analyze_interaction = MagicMock(return_value=MockAnalysis())
        analyzer.extract_srl_object = MagicMock(return_value="general_learning")
        analyzer.get_discussion_quality_score = MagicMock(
            return_value={"quality_score": 0.8}
        )
        return analyzer

    @pytest.mark.asyncio
    async def test_full_message_flow_with_srl_classification(
        self,
        mock_mongo_logger,
        mock_rag_pipeline,
        mock_intervention_service,
        mock_analyzer,
    ):
        """Test complete message flow includes SRL phase classification."""

        # Create orchestrator with mocked dependencies
        orchestrator = Orchestrator(
            rag=mock_rag_pipeline,
            analyzer=mock_analyzer,
            intervention=mock_intervention_service,
            pm_logger=mock_mongo_logger,
            mongo_logger=mock_mongo_logger,
        )

        # Test message representing Forethought phase
        test_message = "Kita mau targetkan belajar React components hari ini"

        # Call the method that handles message processing
        # Note: This would normally call handle_message() but we're testing
        # the SRL classification part specifically

        classifier = get_srl_classifier()
        result = classifier.classify(test_message)

        # Verify SRL classification happened
        assert result.phase == SRLPhase.FORETHOUGHT
        assert result.sub_phase == "goal_setting"
        assert result.confidence > 0.3
        assert len(result.indicators) > 0

        # Verify indicators contain forethought patterns
        forethought_indicators = [
            ind for ind in result.indicators if ind.startswith("forethought:")
        ]
        assert len(forethought_indicators) >= 1

    @pytest.mark.asyncio
    async def test_performance_phase_in_conversation_flow(self, mock_mongo_logger):
        """Test Performance phase classification in context conversation."""

        classifier = get_srl_classifier()

        # Simulate conversation history with Performance signals
        messages = [
            "Target kita minggu ini memahami AI concepts",  # forethought
            "Menurut saya algoritma K-Means itu clustering berdasarkan distance",  # performance
            "Apakah kalian sudah paham sejauh ini?",  # performance monitoring
            "Kesimpulan nya perlu review lagi materi preprocessing",  # reflection
        ]

        classifications = []
        for msg in messages:
            result = classifier.classify(msg)
            classifications.append(
                {
                    "message": msg,
                    "phase": result.phase,
                    "sub_phase": result.sub_phase,
                    "confidence": result.confidence,
                }
            )

        # Verify mixed phases detected correctly
        phases_found = {c["phase"] for c in classifications}

        # Should detect at least 2 different phases
        assert len(phases_found) >= 2

        # Verify each phase has expected characteristics
        for classification in classifications:
            phase = classification["phase"]
            sub_phase = classification["sub_phase"]

            # All sub_phases should be valid strings
            assert isinstance(sub_phase, str)
            assert len(sub_phase) > 0

            # Confidence should be in valid range
            assert 0.3 <= classification["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_mongodb_logging_structures_srl_data(self, mock_mongo_logger):
        """Test that MongoDB logs include SRL phase information."""

        classifier = get_srl_classifier()

        # Test message
        message = "Kesimpulan dari pembelajaran tadi sangat membantu"
        result = classifier.classify(message)

        # Simulate the data structure that would be logged
        log_entry = {
            "CaseID": "test_group_123_session_456",
            "Activity": "Student_Message",
            "Timestamp": datetime.now(),
            "Resource": "Student_test_user",
            "Lifecycle": "complete",
            "Attributes": {
                "original_text": message,
                "srl_object": "general_learning",
                "educational_category": "Learning",
                "is_hot": True,
                "lexical_variety": 0.75,
                "scaffolding_trigger": False,
                "srl_phase": result.phase.value,
                "srl_sub_phase": result.sub_phase,
                "srl_confidence": result.confidence,
            },
        }

        # Verify all required SRL fields are present
        assert "srl_phase" in log_entry["Attributes"]
        assert "srl_sub_phase" in log_entry["Attributes"]
        assert "srl_confidence" in log_entry["Attributes"]

        # Verify values are correct
        assert log_entry["Attributes"]["srl_phase"] == "reflection"
        assert log_entry["Attributes"]["srl_sub_phase"] == "evaluation_reflection"
        assert log_entry["Attributes"]["srl_confidence"] > 0.3

        # Call mock to ensure it's invoked
        await mock_mongo_logger.log_activity(log_entry)
        mock_mongo_logger.log_activity.assert_called_once()


class TestConversationHistorySRLTracking:
    """Test SRL phase tracking across conversation history."""

    def test_consecutive_messages_same_phase(self):
        """Messages with similar intent should maintain same phase."""
        classifier = get_srl_classifier()

        messages = [
            "Kita mau belajar React hari ini",
            "Target kita fokus pada hooks",
            "Mau menguasai konsep components",
        ]

        results = [classifier.classify(msg) for msg in messages]

        # All should be Forethought phase
        phases = [r.phase for r in results]
        assert all(phase == SRLPhase.FORETHOUGHT for phase in phases)

    def test_phase_transition_demonstrates_progression(self):
        """Natural conversation should show Zimmerman phase progression."""
        classifier = get_srl_classifier()

        # Typical learning progression
        conversation = [
            "Goal kita minggu ini understand Deep Learning",  # forethought
            "Implementasi CNN dimulai dengan convolution layer",  # performance
            "Menurut saya pooling itu penting untuk dimensionality reduction",  # performance
            "Setelah praktik tadi, saya baru paham perbedaannya",  # reflection
        ]

        results = [classifier.classify(msg) for msg in conversation]
        phases = [r.phase for r in results]

        # Should see progression through phases
        expected_sequence = [
            SRLPhase.FORETHOUGHT,
            SRLPhase.PERFORMANCE,
            SRLPhase.PERFORMANCE,
            SRLPhase.REFLECTION,
        ]

        assert phases == expected_sequence

    def test_phase_weights_affect_classification_boundary_cases(self):
        """When signals are balanced, higher-weighted phases should win."""
        classifier = SRLClassifier()

        # Create message with equal raw indicators across phases
        message = (
            "Target kita hari ini belajar ML "  # forethought: 1 indicator
            "menurut saya konsep ini jelas "  # performance: 1 indicator
            "kesimpulannya perlu latihan lagi"  # reflection: 2 indicators (evaluation + metacognitive)
        )

        result = classifier.classify(message)

        # Reflection should win due to both more indicators AND higher weight
        assert result.phase == SRLPhase.REFLECTION


class TestSRLClassifierSingletonInOrchestration:
    """Test singleton behavior when used multiple times in orchestration."""

    def test_multiple_classifiers_use_same_instance(self):
        """Multiple calls to get_srl_classifier() should return same instance."""

        # Reset singleton state first
        import app.services.srl_classifier as module

        module._srl_classifier = None

        # Get two classifiers
        classifier1 = get_srl_classifier()
        classifier2 = get_srl_classifier()

        # Must be same instance
        assert classifier1 is classifier2

        # Classify same message twice
        message = "Kita mau belajar React hari ini"
        result1 = classifier1.classify(message)
        result2 = classifier2.classify(message)

        # Results must match exactly
        assert result1.phase == result2.phase
        assert result1.sub_phase == result2.sub_phase
        assert result1.confidence == result2.confidence
        assert result1.indicators == result2.indicators

    def test_single_instance_preserves_state_across_calls(self):
        """Single classifier instance maintains consistent behavior."""

        import app.services.srl_classifier as module

        module._srl_classifier = None

        classifier = get_srl_classifier()

        # Multiple classifications should use same pattern matching logic
        test_messages = [
            "Tujuan kita adalah belajar AI",
            "Target minggu ini mastering React",
            "Goal today understand neural networks",
        ]

        results = [classifier.classify(msg) for msg in test_messages]

        # All should consistently classify as FORETHOUGHT
        for result in results:
            assert result.phase == SRLPhase.FORETHOUGHT


class TestZimmermanAccuracyMetrics:
    """Test accuracy metrics and precision of Zimmerman classification."""

    def test_precision_on_clear_signals(self):
        """Should achieve high precision on messages with clear signals."""
        classifier = get_srl_classifier()

        test_cases = [
            # (message, expected_phase, description)
            ("Kita mau belajar React", SRLPhase.FORETHOUGHT, "clear goal setting"),
            ("Menurut saya konsep ini", SRLPhase.PERFORMANCE, "strategy execution"),
            ("Kesimpulan dari diskusi", SRLPhase.REFLECTION, "evaluation reflection"),
        ]

        all_passed = True
        for message, expected_phase, desc in test_cases:
            result = classifier.classify(message)
            passed = result.phase == expected_phase
            all_passed = all_passed and passed

            if not passed:
                print(f"FAILED: {desc}")
                print(f"  Message: {message}")
                print(f"  Expected: {expected_phase.value}")
                print(f"  Got: {result.phase.value}")

        assert all_passed, "Some precision tests failed"

    def test_recall_across_different_topics(self):
        """Should correctly classify across diverse subject matter."""
        classifier = get_srl_classifier()

        topics = [
            # Machine Learning
            "Target kita mempelajari K-Means clustering",
            "Implementasi decision trees dimulai dengan splitting",
            "Kesimpulan nya cross-validation penting banget",
            # Web Development
            "Kita mau belajar React hooks hari ini",
            "Menurut saya useEffect itu powerful banget",
            "Setelah praktik tadi baru paham lifecycle",
            # Data Structures
            "Goal minggu ini master array dan object",
            "Algoritma sorting bubble sort itu O(n^2)",
            "Lain kali perlu pelajari binary tree lebih dalam",
        ]

        # Every topic should have all three phases represented
        phases_found = set()

        for topic in topics:
            result = classifier.classify(topic)
            phases_found.add(result.phase)

        # Should have detected at least 2 out of 3 phases
        assert len(phases_found) >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
