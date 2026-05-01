import math

from app.services.conformance_checker import ConformanceChecker, ConformanceResult


def test_perfect_sequence_is_conformant():
    result = ConformanceChecker().check([
        "GOAL_SETTING",
        "STUDENT_MESSAGE",
        "BOT_RESPONSE",
        "REFLECTION_SUBMITTED",
    ])

    assert isinstance(result, ConformanceResult)
    assert result.is_conformant is True
    assert math.isclose(result.alignment_score, 1.0)
    assert math.isclose(result.token_replay_score, 1.0)
    assert result.missing_activities == []
    assert result.extra_activities == []


def test_empty_sequence_is_not_conformant():
    result = ConformanceChecker().check([])

    assert result.is_conformant is False
    assert math.isclose(result.alignment_score, 0.0)
    assert math.isclose(result.token_replay_score, 0.0)
    assert result.missing_activities == [
        "GOAL_SETTING",
        "STUDENT_MESSAGE",
        "BOT_RESPONSE",
        "REFLECTION_SUBMITTED",
    ]
    assert result.alignment_details == []


def test_partial_sequence_reports_last_two_missing():
    result = ConformanceChecker().check(["GOAL_SETTING", "STUDENT_MESSAGE"])

    assert result.is_conformant is False
    assert math.isclose(result.alignment_score, 0.4)
    assert math.isclose(result.token_replay_score, 0.5)
    assert result.missing_activities == ["BOT_RESPONSE", "REFLECTION_SUBMITTED"]
    assert result.extra_activities == []


def test_out_of_order_sequence_is_not_conformant():
    result = ConformanceChecker().check([
        "STUDENT_MESSAGE",
        "GOAL_SETTING",
        "BOT_RESPONSE",
        "REFLECTION_SUBMITTED",
    ])

    assert result.is_conformant is False
    assert math.isclose(result.alignment_score, 0.35)
    assert math.isclose(result.token_replay_score, 0.25)
    assert result.missing_activities == []


def test_extra_activities_mixed_in_are_reported():
    result = ConformanceChecker().check([
        "GOAL_SETTING",
        "PING",
        "STUDENT_MESSAGE",
        "BOT_RESPONSE",
        "SIDE_QUEST",
        "REFLECTION_SUBMITTED",
    ])

    assert result.is_conformant is True
    assert math.isclose(result.alignment_score, 1.0)
    assert math.isclose(result.token_replay_score, 0.9)
    assert result.extra_activities == ["PING", "SIDE_QUEST"]


def test_single_activity_only_is_not_conformant():
    result = ConformanceChecker().check(["GOAL_SETTING"])

    assert result.is_conformant is False
    assert math.isclose(result.alignment_score, 0.05)
    assert math.isclose(result.token_replay_score, 0.25)
    assert result.missing_activities == ["STUDENT_MESSAGE", "BOT_RESPONSE", "REFLECTION_SUBMITTED"]


def test_duplicate_activity_keeps_conformance_when_all_expected_exist():
    result = ConformanceChecker().check([
        "GOAL_SETTING",
        "STUDENT_MESSAGE",
        "STUDENT_MESSAGE",
        "BOT_RESPONSE",
        "REFLECTION_SUBMITTED",
    ])

    assert result.is_conformant is True
    assert math.isclose(result.alignment_score, 1.0)
    assert math.isclose(result.token_replay_score, 1.0)
    assert result.extra_activities == []


def test_all_expected_plus_many_extras_reduces_token_replay_score():
    result = ConformanceChecker().check([
        "GOAL_SETTING",
        "X1",
        "STUDENT_MESSAGE",
        "X2",
        "BOT_RESPONSE",
        "X3",
        "REFLECTION_SUBMITTED",
        "X4",
        "X5",
    ])

    assert result.is_conformant is True
    assert math.isclose(result.alignment_score, 0.85)
    assert math.isclose(result.token_replay_score, 0.75)
    assert result.extra_activities == ["X1", "X2", "X3", "X4", "X5"]


def test_alignment_details_include_matched_entries():
    result = ConformanceChecker().check([
        "GOAL_SETTING",
        "STUDENT_MESSAGE",
        "BOT_RESPONSE",
        "REFLECTION_SUBMITTED",
    ])

    assert "matched:GOAL_SETTING" in result.alignment_details
    assert "matched:STUDENT_MESSAGE" in result.alignment_details


def test_alignment_details_include_out_of_order_entries():
    result = ConformanceChecker().check([
        "STUDENT_MESSAGE",
        "GOAL_SETTING",
        "BOT_RESPONSE",
        "REFLECTION_SUBMITTED",
    ])

    assert "out_of_order:STUDENT_MESSAGE" in result.alignment_details
    assert "out_of_order:BOT_RESPONSE" in result.alignment_details


def test_alignment_details_include_unexpected_entries():
    result = ConformanceChecker().check(["GOAL_SETTING", "PING"])

    assert "unexpected:PING" in result.alignment_details


def test_only_extra_activity_is_not_conformant():
    result = ConformanceChecker().check(["PING"])

    assert result.is_conformant is False
    assert math.isclose(result.alignment_score, 0.0)
    assert math.isclose(result.token_replay_score, 0.0)
    assert result.extra_activities == ["PING"]


def test_token_replay_score_penalizes_extra_events_only():
    result = ConformanceChecker().check([
        "GOAL_SETTING",
        "PING",
        "STUDENT_MESSAGE",
        "BOT_RESPONSE",
        "REFLECTION_SUBMITTED",
    ])

    assert math.isclose(result.alignment_score, 1.0)
    assert math.isclose(result.token_replay_score, 0.95)


def test_missing_activities_for_out_of_order_sequence_can_be_empty():
    result = ConformanceChecker().check([
        "STUDENT_MESSAGE",
        "GOAL_SETTING",
        "BOT_RESPONSE",
        "REFLECTION_SUBMITTED",
    ])

    assert result.missing_activities == []


def test_extra_activities_preserve_observed_order():
    result = ConformanceChecker().check([
        "GOAL_SETTING",
        "PING",
        "STUDENT_MESSAGE",
        "BOT_RESPONSE",
        "SIDE_QUEST",
        "REFLECTION_SUBMITTED",
    ])

    assert result.extra_activities == ["PING", "SIDE_QUEST"]
