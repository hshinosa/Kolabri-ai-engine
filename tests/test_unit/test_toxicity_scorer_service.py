import math

import pytest

from app.services.toxicity_scorer import ToxicityScorer, ToxicityResult


def test_clean_text_is_not_toxic():
    result = ToxicityScorer().score("Mari fokus pada solusi yang baik.")

    assert isinstance(result, ToxicityResult)
    assert result.is_toxic is False
    assert math.isclose(result.score, 0.0)
    assert result.labels == []


def test_single_bodoh_term_is_toxic():
    result = ToxicityScorer().score("kamu bodoh")

    assert result.is_toxic is True
    assert math.isclose(result.score, 0.25)
    assert result.labels == ["bodoh"]


def test_multiple_terms_accumulate_score():
    result = ToxicityScorer().score("bodoh goblok")

    assert result.is_toxic is True
    assert math.isclose(result.score, 0.6)
    assert result.labels == ["bodoh", "goblok"]


def test_score_is_capped_at_one():
    result = ToxicityScorer().score("bodoh goblok tolol idiot stupid moron fuck shit anjing")

    assert result.is_toxic is True
    assert math.isclose(result.score, 1.0)
    assert len(result.labels) == 9


def test_detection_is_case_insensitive():
    result = ToxicityScorer().score("BODOH")

    assert result.is_toxic is True
    assert math.isclose(result.score, 0.25)
    assert result.labels == ["bodoh"]


def test_empty_string_is_not_toxic():
    result = ToxicityScorer().score("")

    assert result.is_toxic is False
    assert math.isclose(result.score, 0.0)
    assert result.labels == []


@pytest.mark.parametrize(
    ("text", "expected_score", "label"),
    [
        ("bodoh", 0.25, "bodoh"),
        ("goblok", 0.35, "goblok"),
        ("tolol", 0.35, "tolol"),
        ("idiot", 0.3, "idiot"),
        ("stupid", 0.25, "stupid"),
        ("moron", 0.3, "moron"),
        ("fuck", 0.4, "fuck"),
        ("shit", 0.3, "shit"),
        ("anjing", 0.3, "anjing"),
    ],
)
def test_each_toxic_term_individually(text, expected_score, label):
    result = ToxicityScorer().score(text)

    assert result.is_toxic is True
    assert math.isclose(result.score, expected_score)
    assert result.labels == [label]


def test_partial_word_substring_match_counts():
    result = ToxicityScorer().score("stupidity is harmful")

    assert result.is_toxic is True
    assert math.isclose(result.score, 0.25)
    assert result.labels == ["stupid"]


def test_labels_contain_all_matched_terms():
    result = ToxicityScorer().score("anjing dan idiot itu kasar")

    assert result.labels == ["idiot", "anjing"]
    assert math.isclose(result.score, 0.6)
