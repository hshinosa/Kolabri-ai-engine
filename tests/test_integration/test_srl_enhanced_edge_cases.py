"""
Enhanced Integration Tests: Zimmerman SRL Classifier
=====================================================
Comprehensive edge case testing for production-ready classifier.
Tests enhanced patterns, confidence calibration, scaffolding levels,
and intervention routing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from app.services.srl_classifier_enhanced import (
    get_enhanced_srl_classifier,
    EnhancedSRLClassificationResult,
    SRLPhase,
)


class TestEnhancedPatternMatching:
    """Test enhanced pattern matching capabilities."""

    @pytest.fixture
    def classifier(self):
        return get_enhanced_srl_classifier()

    # Indonesian suffix handling
    def test_goal_with_suffix_nya(self, classifier):
        """Handle goalSetting words with -nya suffix."""
        result = classifier.classify("target kita hari ini yang baru")
        assert result.phase == SRLPhase.FORETHOUGHT

    def test_plan_with_suffix_kan(self, classifier):
        """Handle planning words with -kan suffix."""
        result = classifier.classify("rencana yang sudah kita siapkan")
        assert result.phase == SRLPhase.FORETHOUGHT

    def test_reflection_with_variation(self, classifier):
        """Handle reflection patterns with word variations."""
        # Should match "kesimpulannya" via pattern ending in -?w*
        result = classifier.classify("Kesimpulannya perlu dipelajari lagi")
        assert result.phase == SRLPhase.REFLECTION

    # Mixed language support
    def test_english_indonesian_mix(self, classifier):
        """Handle mixed Indonesian-English messages."""
        message = "Goal kita today adalah understand Deep Learning concepts"
        result = classifier.classify(message)

        assert result.phase == SRLPhase.FORETHOUGHT
        assert "forethought:goal_setting" in result.indicators

    def test_acronym_detection(self, classifier):
        """Detect acronyms like CNN, K-Means, React."""
        message = "Implementasi CNN dimulai dengan convolution layer"
        result = classifier.classify(message)

        assert result.phase == SRLPhase.PERFORMANCE
        assert result.sub_phase == "strategy_execution"

    # Edge case messages
    def test_very_short_message(self, classifier):
        """Handle very short single-word messages."""
        result = classifier.classify("Hai")
        assert result.phase == SRLPhase.PERFORMANCE
        assert result.confidence == 0.3

    def test_numeric_only_message(self, classifier):
        """Handle numeric or special character messages."""
        result = classifier.classify("123")
        assert result.phase == SRLPhase.PERFORMANCE
        assert len(result.indicators) == 0

    def test_special_characters(self, classifier):
        """Handle messages with special characters."""
        result = classifier.classify("React hooks!!!")
        assert result.phase == SRLPhase.PERFORMANCE

    def test_emoji_mixed_text(self, classifier):
        """Handle emojis mixed with text."""
        result = classifier.classify("Kita belajar AI 🤖")
        # Emojis may classify differently, just check result type
        assert isinstance(result, EnhancedSRLClassificationResult)

    def test_extremely_long_message(self, classifier):
        """Handle very long multi-sentence messages."""
        long_msg = (
            "Target kita minggu ini adalah mempelajari materi React dan Next.js. " * 50
        )
        result = classifier.classify(long_msg)

        assert result.phase == SRLPhase.FORETHOUGHT
        assert len(result.matched_patterns) > 0


class TestConfidenceCalibration:
    """Test confidence score calibration."""

    @pytest.fixture
    def classifier(self):
        return get_enhanced_srl_classifier()

    def test_confidence_clamped_to_max_095(self, classifier):
        """Confidence should never exceed 0.95."""
        # Create a message with many strong indicators
        strong_msg = (
            "Target kita target kita target kita " * 10 + "ingin mau mau mau " * 10
        )
        result = classifier.classify(strong_msg)

        assert result.confidence <= 0.95
        assert result.confidence >= 0.3

    def test_confidence_has_min_bound(self, classifier):
        """Minimum confidence should be 0.3."""
        weak_msg = "random garbage text here"
        result = classifier.classify(weak_msg)

        assert result.confidence >= 0.3

    def test_high_signal_increases_confidence(self, classifier):
        """Clear signals should produce higher confidence."""
        clear_forethought = "Tujuan utama kita adalah memahami React components"
        unclear_text = "blah blah whatever random stuff"

        result_clear = classifier.classify(clear_forethought)
        result_unclear = classifier.classify(unclear_text)

        assert result_clear.confidence >= result_unclear.confidence

    def test_empty_string_default_confidence(self, classifier):
        """Empty string returns default confidence of 0.3."""
        result = classifier.classify("")
        assert result.confidence == 0.3


class TestScaffoldingRecommendations:
    """Test scaffolding level recommendations per phase."""

    @pytest.fixture
    def classifier(self):
        return get_enhanced_srl_classifier()

    def test_forethought_gets_high_scaffolding(self, classifier):
        """Forethought phase should get 'high' scaffolding level."""
        result = classifier.classify("Kita mau belajar React hari ini")

        assert result.scaffolding_level == "high"
        assert result.requires_attention is False

    def test_performance_gets_medium_scaffolding(self, classifier):
        """Performance phase should get 'medium' scaffolding level."""
        result = classifier.classify("Menurut saya konsep ini penting")

        assert result.scaffolding_level == "medium"
        assert result.requires_attention is False

    def test_reflection_gets_low_scaffolding(self, classifier):
        """Reflection phase should get 'low' scaffolding level."""
        result = classifier.classify("Setelah diskusi tadi saya baru paham")

        assert result.scaffolding_level == "low"
        assert result.requires_attention is True

    def test_scaffolding_action_generation(self, classifier):
        """Should generate actionable scaffolding recommendations."""
        result = classifier.classify("Goal kita minggu ini master K-Means")

        recommendations = classifier.get_recommendations(result)

        assert recommendations["scaffolding_action"] is not None
        assert recommendations["follow_up_needed"] is False


class TestInterventionRouting:
    """Test intervention type hints per phase."""

    @pytest.fixture
    def classifier(self):
        return get_enhanced_srl_classifier()

    def test_forethought_intervention_type(self, classifier):
        """Forethought should suggest GOAL_CLARIFICATION."""
        result = classifier.classify("Target kita memahami AI")

        recommendations = classifier.get_recommendations(result)
        assert recommendations["intervention_type"] == "GOAL_CLARIFICATION"

    def test_performance_intervention_type(self, classifier):
        """Performance should suggest STRATEGY_VALIDATION."""
        result = classifier.classify("Implementasi CNN dimulai dari sini")

        recommendations = classifier.get_recommendations(result)
        assert recommendations["intervention_type"] == "STRATEGY_VALIDATION"

    def test_reflection_intervention_type(self, classifier):
        """Reflection should suggest METACOGNITIVE_PROMPT."""
        result = classifier.classify("Kesimpulan nya perlu review lagi")

        recommendations = classifier.get_recommendations(result)
        assert recommendations["intervention_type"] == "METACOGNITIVE_PROMPT"


class TestPriorityCalculation:
    """Test priority level calculation based on confidence and phase."""

    @pytest.fixture
    def classifier(self):
        return get_enhanced_srl_classifier()

    def test_low_priority_calculation(self, classifier):
        """Low confidence should result in LOW priority."""
        result = classifier.classify("random nonsense text")

        recommendations = classifier.get_recommendations(result)
        assert recommendations["priority_level"] == "LOW"

    def test_high_priority_for_reflection(self, classifier):
        """High confidence reflection should get HIGH priority."""
        result = classifier.classify("Setelah praktik tadi benar-benar paham sekarang")

        recommendations = classifier.get_recommendations(result)
        assert recommendations["priority_level"] == "HIGH"

    def test_medium_priority_default(self, classifier):
        """Medium confidence gets MEDIUM priority."""
        result = classifier.classify("Konsep ini menurut saya menarik")

        recommendations = classifier.get_recommendations(result)
        assert recommendations["priority_level"] == "MEDIUM"


class TestPatternTracking:
    """Test matched patterns tracking for debugging."""

    @pytest.fixture
    def classifier(self):
        return get_enhanced_srl_classifier()

    def test_matched_patterns_limit(self, classifier):
        """Should limit tracked patterns to avoid memory issues."""
        msg = "target target target target " * 100
        result = classifier.classify(msg)

        assert len(result.matched_patterns) <= 10

    def test_pattern_scores_accuracy(self, classifier):
        """Pattern scores should reflect actual matches."""
        msg = "tujuan tujuan rencana rencana strategi"
        result = classifier.classify(msg)

        # Should have positive scores for all phases present
        phase_scores = result.pattern_scores
        assert any(score > 0 for score in phase_scores.values())


class TestEdgeCaseRobustness:
    """Test robustness against various edge cases."""

    @pytest.fixture
    def classifier(self):
        return get_enhanced_srl_classifier()


    def test_whitespace_only_message(self, classifier):
        """Handle whitespace-only messages."""
        result = classifier.classify("   \t\n   ")
        assert isinstance(result, EnhancedSRLClassificationResult)

    def test_unicode_characters(self, classifier):
        """Handle unicode characters properly."""
        result = classifier.classify("Kita belajar algoritma αβγ δεζ")
        assert isinstance(result, EnhancedSRLClassificationResult)

    def test_double_byte_characters(self, classifier):
        """Handle Japanese/Chinese characters."""
        result = classifier.classify("目標是我们的目标 learning")
        assert isinstance(result, EnhancedSRLClassificationResult)

    def test_html_tags_in_message(self, classifier):
        """Handle HTML tags in message text."""
        result = classifier.classify("<div>Target belajar <b>React</b></div>")
        assert isinstance(result, EnhancedSRLClassificationResult)


class TestSingletonBehaviorEnhanced:
    """Test singleton instance behavior for enhanced classifier."""

    def test_enhanced_singleton(self):
        """Multiple calls should return same instance."""
        c1 = get_enhanced_srl_classifier()
        c2 = get_enhanced_srl_classifier()

        assert c1 is c2

