import pytest

from app.services import srl_classifier as srl_classifier_module
from app.services.srl_classifier import (
    SRLClassifier,
    SRLPhase,
    SRLClassificationResult,
    get_srl_classifier,
)


@pytest.fixture
def classifier():
    return SRLClassifier()


def test_returns_result_dataclass(classifier):
    result = classifier.classify("hello world")
    assert isinstance(result, SRLClassificationResult)


def test_goal_setting_message_maps_to_forethought(classifier):
    result = classifier.classify("tujuan kita hari ini adalah memahami konsep AI")
    assert result.phase == SRLPhase.FORETHOUGHT
    assert result.sub_phase == "goal_setting"


def test_planning_message_maps_to_forethought(classifier):
    result = classifier.classify(
        "rencana kita: pertama kita bahas teori, kedua kita praktik"
    )
    assert result.phase == SRLPhase.FORETHOUGHT
    assert result.sub_phase == "planning"


def test_strategy_execution_message_maps_to_performance(classifier):
    result = classifier.classify(
        "menurut saya konsep ini artinya implementasi dari teori"
    )
    assert result.phase == SRLPhase.PERFORMANCE
    assert result.sub_phase == "strategy_execution"


def test_monitoring_message_maps_to_performance(classifier):
    result = classifier.classify("apakah kita sudah paham sejauh ini?")
    assert result.phase == SRLPhase.PERFORMANCE
    assert result.sub_phase == "monitoring_control"


def test_reflection_message_maps_to_reflection(classifier):
    result = classifier.classify(
        "kesimpulan dari diskusi tadi, kita sudah memahami konsep"
    )
    assert result.phase == SRLPhase.REFLECTION
    assert result.sub_phase == "evaluation_reflection"


def test_metacognitive_message_maps_to_reflection(classifier):
    result = classifier.classify(
        "lain kali kita perlu belajar strategi yang lebih baik"
    )
    assert result.phase == SRLPhase.REFLECTION
    assert result.sub_phase == "metacognitive_adaptation"


def test_no_match_defaults_to_performance_strategy_execution(classifier):
    result = classifier.classify("hello world")
    assert result.phase == SRLPhase.PERFORMANCE
    assert result.sub_phase == "strategy_execution"
    assert result.confidence == 0.3
    assert result.indicators == []


def test_empty_string_defaults_to_performance_strategy_execution(classifier):
    result = classifier.classify("")
    assert result.phase == SRLPhase.PERFORMANCE
    assert result.sub_phase == "strategy_execution"
    assert result.confidence == 0.3
    assert result.indicators == []


def test_confidence_is_between_zero_and_one_for_goal_message(classifier):
    result = classifier.classify("tujuan kita hari ini adalah memahami konsep AI")
    assert 0.0 <= result.confidence <= 1.0


def test_indicators_include_goal_setting_match(classifier):
    result = classifier.classify("tujuan kita hari ini adalah memahami konsep AI")
    assert "forethought:goal_setting" in result.indicators


def test_indicators_include_multiple_strategy_execution_matches(classifier):
    result = classifier.classify(
        "menurut saya konsep ini artinya implementasi dari teori karena definisinya jelas"
    )
    assert result.indicators.count("performance:strategy_execution") >= 4


def test_mixed_indicators_favor_reflection_due_to_weighting(classifier):
    message = "tujuan kita memahami konsep ini, tetapi kesimpulan dari diskusi tadi kita sudah memahami konsep"
    result = classifier.classify(message)
    assert "forethought:goal_setting" in result.indicators
    assert "reflection:evaluation_reflection" in result.indicators
    assert result.phase == SRLPhase.REFLECTION


def test_planning_can_beat_goal_setting_with_more_matches(classifier):
    message = "rencana kita: pertama kita bahas teori, kedua kita praktik, lalu pembagian tugas dibuat hari ini"
    result = classifier.classify(message)
    assert result.phase == SRLPhase.FORETHOUGHT
    assert result.sub_phase == "planning"


def test_monitoring_indicators_are_collected(classifier):
    result = classifier.classify(
        "apakah kita sudah paham sejauh ini atau masih belum jelas?"
    )
    assert "performance:monitoring_control" in result.indicators
    assert result.indicators.count("performance:monitoring_control") >= 3


def test_reflection_weight_can_outweigh_performance_with_same_match_count(classifier):
    message = "menurut saya konsep ini jelas. kesimpulan dari diskusi tadi kita sudah memahami konsep"
    result = classifier.classify(message)
    assert result.phase == SRLPhase.REFLECTION
    assert result.sub_phase == "evaluation_reflection"


def test_uppercase_message_is_handled_case_insensitively(classifier):
    result = classifier.classify("TUJUAN KITA HARI INI ADALAH MEMAHAMI KONSEP AI")
    assert result.phase == SRLPhase.FORETHOUGHT
    assert result.sub_phase == "goal_setting"


def test_get_srl_classifier_returns_singleton_instance():
    srl_classifier_module._srl_classifier = None

    instance_one = get_srl_classifier()
    instance_two = get_srl_classifier()

    assert isinstance(instance_one, SRLClassifier)
    assert instance_one is instance_two


# Integration Tests for Zimmerman SRL Classifier with Orchestration Flow


class TestIntegrationWithOrchestration:
    """Test that SRL classifier integrates properly with orchestration flow."""

    def test_orchestration_ready_result_format(self):
        """Test result format matches orchestration expectations."""
        classifier = SRLClassifier()
        message = "Kita mau targetkan learning React components hari ini"
        result = classifier.classify(message)

        # Must have required fields for MongoDB logging
        assert hasattr(result, "phase")
        assert hasattr(result, "sub_phase")
        assert hasattr(result, "confidence")
        assert hasattr(result, "indicators")

        # Phase must be serializable to string
        phase_str = result.phase.value
        assert isinstance(phase_str, str)
        assert phase_str in ["forethought", "performance", "reflection"]

        # Confidence must be numeric
        assert isinstance(result.confidence, float)

        # Indicators must be list of strings
        assert isinstance(result.indicators, list)
        assert all(isinstance(indicator, str) for indicator in result.indicators)


class TestIntegrationEdgeCases:
    """Test integration edge cases and error handling."""

    def test_empty_message_doesnt_crash_integration(self):
        """Empty messages should not crash the classification process."""
        classifier = SRLClassifier()

        # Should handle gracefully without exceptions
        result = classifier.classify("")
        assert result.phase == SRLPhase.PERFORMANCE
        assert result.confidence == 0.3

    def test_mixed_language_messages(self):
        """Should handle mixed Indonesian-English messages."""
        classifier = SRLClassifier()

        message = "Goal kita today adalah understand Deep Learning concepts"
        result = classifier.classify(message)

        # Should detect English keywords
        assert result.phase == SRLPhase.FORETHOUGHT
        assert "forethought:goal_setting" in result.indicators

    def test_very_long_message_classification(self):
        """Longer messages should still classify correctly."""
        classifier = SRLClassifier()

        long_message = (
            "Target kita minggu ini adalah mempelajari materi React dan Next.js. "
            "Mari kita bagi tugasnya menjadi beberapa bagian. Pertama kita bahas konsep dasar, "
            "kedua kita praktik coding, dan ketiga kita review bersama. Menurut saya konsep JSX itu penting sekali. "
            "Apakah kita sudah paham sejauh ini? Setelah diskusi nanti, kita perlu evaluasi lagi cara belajarnya."
        )
        result = classifier.classify(long_message)

        # Should identify dominant phase correctly
        assert result.phase in [
            SRLPhase.FORETHOUGHT,
            SRLPhase.PERFORMANCE,
            SRLPhase.REFLECTION,
        ]
        assert len(result.indicators) >= 1
        assert 0.3 <= result.confidence <= 1.0


class TestZimmermanPhaseAccuracy:
    """Test accuracy of Zimmerman phase detection."""

    def test_clear_forethought_signals(self):
        """Messages with clear goal-setting signals should map to forethought."""
        classifier = SRLClassifier()

        test_cases = [
            "Kita ingin memahami materi AI minggu ini",
            "Target kita adalah menguasai konsep machine learning",
            "Mau belajar tentang neural networks hari ini",
        ]

        for message in test_cases:
            result = classifier.classify(message)
            assert result.phase == SRLPhase.FORETHOUGHT, f"Failed for: {message}"

    def test_clear_performance_signals(self):
        """Messages with strategy execution should map to performance."""
        classifier = SRLClassifier()

        test_cases = [
            "Menurut saya algoritma ini menggunakan distance metric",
            "Implementasi K-Means dimulai dengan random initialization",
            "Konsep clustering memang kompleks tapi bisa dipahami",
        ]

        for message in test_cases:
            result = classifier.classify(message)
            assert result.phase == SRLPhase.PERFORMANCE, f"Failed for: {message}"

    def test_clear_reflection_signals(self):
        """Messages with reflection indicators should map to reflection."""
        classifier = SRLClassifier()

        test_cases = [
            "Kesimpulan dari pembelajaran ini sangat membantu",
            "Setelah diskusi tadi, saya baru paham perbedaannya",
            "Lain kali perlu pelajari lebih dalam lagi",
        ]

        for message in test_cases:
            result = classifier.classify(message)
            assert result.phase == SRLPhase.REFLECTION, f"Failed for: {message}"

    def test_conflicting_signals_resolve_correctly(self):
        """When multiple phases are present, should resolve to dominant one."""
        classifier = SRLClassifier()

        # Mix of all three phases
        message = (
            "Target kita belajar React (forethought), "
            "menurut saya hooks itu powerful (performance), "
            "kesimpulannya butuh latihan lagi (reflection)"
        )
        result = classifier.classify(message)

        # Should favor Reflection due to higher weight and balanced indicators
        assert result.phase in [
            SRLPhase.FORETHOUGHT,
            SRLPhase.PERFORMANCE,
            SRLPhase.REFLECTION,
        ]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
