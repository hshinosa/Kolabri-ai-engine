import pytest

from app.services.conformance_checker import ConformanceChecker


@pytest.fixture
def checker():
    return ConformanceChecker()


def test_perfect_sequence_is_conformant(checker):
    result = checker.check(checker.EXPECTED_SEQUENCE)

    assert result.is_conformant is True
    assert result.alignment_score == 1.0
    assert result.token_replay_score == 1.0
    assert result.missing_activities == []
    assert result.extra_activities == []


def test_perfect_sequence_details_are_all_matched(checker):
    result = checker.check(checker.EXPECTED_SEQUENCE)

    assert result.alignment_details == [
        "matched:GOAL_SETTING",
        "matched:STUDENT_MESSAGE",
        "matched:BOT_RESPONSE",
        "matched:REFLECTION_SUBMITTED",
    ]


def test_empty_sequence_marks_all_missing(checker):
    result = checker.check([])

    assert result.is_conformant is False
    assert result.alignment_score == 0.0
    assert result.token_replay_score == 0.0
    assert result.missing_activities == checker.EXPECTED_SEQUENCE
    assert result.extra_activities == []
    assert result.alignment_details == []


def test_partial_sequence_reports_last_two_missing(checker):
    result = checker.check(["GOAL_SETTING", "STUDENT_MESSAGE"])

    assert result.is_conformant is False
    assert result.alignment_score == 0.4
    assert result.token_replay_score == 0.5
    assert result.missing_activities == ["BOT_RESPONSE", "REFLECTION_SUBMITTED"]
    assert result.extra_activities == []


def test_out_of_order_sequence_marks_alignment_details(checker):
    result = checker.check([
        "STUDENT_MESSAGE",
        "GOAL_SETTING",
        "BOT_RESPONSE",
        "REFLECTION_SUBMITTED",
    ])

    assert result.is_conformant is False
    assert result.alignment_score == 0.35
    assert "out_of_order:STUDENT_MESSAGE" in result.alignment_details
    assert "out_of_order:BOT_RESPONSE" in result.alignment_details
    assert "out_of_order:REFLECTION_SUBMITTED" in result.alignment_details


def test_extra_activities_are_reported(checker):
    result = checker.check(checker.EXPECTED_SEQUENCE + ["UNEXPECTED_EVENT"])

    assert result.extra_activities == ["UNEXPECTED_EVENT"]
    assert result.missing_activities == []
    assert result.is_conformant is True
    assert result.token_replay_score == 0.95


def test_extra_activities_append_unexpected_details(checker):
    result = checker.check(["GOAL_SETTING", "SIDE_QUEST"])

    assert result.extra_activities == ["SIDE_QUEST"]
    assert "unexpected:SIDE_QUEST" in result.alignment_details


def test_single_activity_only_has_low_scores(checker):
    result = checker.check(["GOAL_SETTING"])

    assert result.is_conformant is False
    assert result.alignment_score == 0.05
    assert result.token_replay_score == 0.25
    assert result.missing_activities == ["STUDENT_MESSAGE", "BOT_RESPONSE", "REFLECTION_SUBMITTED"]


def test_duplicate_expected_activity_is_not_extra(checker):
    result = checker.check([
        "GOAL_SETTING",
        "GOAL_SETTING",
        "STUDENT_MESSAGE",
        "BOT_RESPONSE",
        "REFLECTION_SUBMITTED",
    ])

    assert result.extra_activities == []
    assert result.missing_activities == []
    assert result.is_conformant is True
    assert "out_of_order:GOAL_SETTING" in result.alignment_details


def test_many_extra_activities_reduce_alignment_score(checker):
    observed = checker.EXPECTED_SEQUENCE + [f"EXTRA_{index}" for index in range(10)]
    result = checker.check(observed)

    assert result.is_conformant is False
    assert result.alignment_score == 0.6
    assert result.token_replay_score == 0.5
    assert len(result.extra_activities) == 10


def test_reversed_sequence_is_not_conformant(checker):
    result = checker.check(list(reversed(checker.EXPECTED_SEQUENCE)))

    assert result.is_conformant is False
    assert result.alignment_score == 0.35
    assert result.token_replay_score == 0.25
    assert result.missing_activities == []
    assert result.alignment_details.count("matched:GOAL_SETTING") == 1


def test_only_unexpected_activities_have_no_ordered_hits(checker):
    result = checker.check(["A", "B", "C"])

    assert result.is_conformant is False
    assert result.alignment_score == 0.0
    assert result.token_replay_score == 0.0
    assert result.missing_activities == checker.EXPECTED_SEQUENCE
    assert result.extra_activities == ["A", "B", "C"]


def test_alignment_score_is_clamped_to_one(checker):
    result = checker.check(checker.EXPECTED_SEQUENCE + ["EXTRA"])

    assert 0.0 <= result.alignment_score <= 1.0
    assert result.alignment_score == 1.0


def test_alignment_score_is_clamped_to_zero(checker):
    result = checker.check([f"EXTRA_{index}" for index in range(20)])

    assert 0.0 <= result.alignment_score <= 1.0
    assert result.alignment_score == 0.0


def test_token_replay_score_is_clamped_to_one(checker):
    result = checker.check(checker.EXPECTED_SEQUENCE)

    assert 0.0 <= result.token_replay_score <= 1.0
    assert result.token_replay_score == 1.0


def test_token_replay_score_is_clamped_to_zero(checker):
    result = checker.check([f"EXTRA_{index}" for index in range(30)])

    assert 0.0 <= result.token_replay_score <= 1.0
    assert result.token_replay_score == 0.0
