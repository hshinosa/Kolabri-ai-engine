import pytest

from app.services import srl_classifier as srl_classifier_module
from app.services.srl_classifier import SRLClassifier, SRLPhase, SRLClassificationResult, get_srl_classifier


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
    result = classifier.classify("rencana kita: pertama kita bahas teori, kedua kita praktik")
    assert result.phase == SRLPhase.FORETHOUGHT
    assert result.sub_phase == "planning"


def test_strategy_execution_message_maps_to_performance(classifier):
    result = classifier.classify("menurut saya konsep ini artinya implementasi dari teori")
    assert result.phase == SRLPhase.PERFORMANCE
    assert result.sub_phase == "strategy_execution"


def test_monitoring_message_maps_to_performance(classifier):
    result = classifier.classify("apakah kita sudah paham sejauh ini?")
    assert result.phase == SRLPhase.PERFORMANCE
    assert result.sub_phase == "monitoring_control"


def test_reflection_message_maps_to_reflection(classifier):
    result = classifier.classify("kesimpulan dari diskusi tadi, kita sudah memahami konsep")
    assert result.phase == SRLPhase.REFLECTION
    assert result.sub_phase == "evaluation_reflection"


def test_metacognitive_message_maps_to_reflection(classifier):
    result = classifier.classify("lain kali kita perlu belajar strategi yang lebih baik")
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
    result = classifier.classify("menurut saya konsep ini artinya implementasi dari teori karena definisinya jelas")
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
    result = classifier.classify("apakah kita sudah paham sejauh ini atau masih belum jelas?")
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
