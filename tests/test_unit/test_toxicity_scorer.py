import pytest

from app.services.toxicity_scorer import ToxicityScorer


@pytest.fixture
def scorer():
    return ToxicityScorer()


def test_clean_text_has_zero_score(scorer):
    result = scorer.score("Mari kita diskusikan solusi database secara tenang.")

    assert result.is_toxic is False
    assert result.score == 0.0
    assert result.labels == []


def test_bodoh_is_toxic(scorer):
    result = scorer.score("Kamu bodoh")

    assert result.is_toxic is True
    assert result.score == 0.25
    assert result.labels == ["bodoh"]


def test_goblok_is_toxic(scorer):
    result = scorer.score("Dasar goblok")

    assert result.is_toxic is True
    assert result.score == 0.35
    assert result.labels == ["goblok"]


def test_fuck_is_toxic(scorer):
    result = scorer.score("fuck this bug")

    assert result.is_toxic is True
    assert result.score == 0.4
    assert result.labels == ["fuck"]


def test_multiple_toxic_terms_accumulate(scorer):
    result = scorer.score("Kamu bodoh dan goblok")

    assert result.score == 0.6
    assert result.labels == ["bodoh", "goblok"]


def test_score_is_capped_at_one(scorer):
    result = scorer.score("bodoh goblok tolol idiot stupid moron fuck shit anjing")

    assert result.score == 1.0
    assert result.is_toxic is True


def test_matching_is_case_insensitive(scorer):
    result = scorer.score("BODOH SEKALI")

    assert result.score == 0.25
    assert result.labels == ["bodoh"]


def test_partial_word_match_counts(scorer):
    result = scorer.score("Sikap bodohnya membuat diskusi berhenti")

    assert result.score == 0.25
    assert result.labels == ["bodoh"]


def test_non_toxic_indonesian_text_is_allowed(scorer):
    result = scorer.score("Saya setuju kita perlu mengevaluasi argumen ini dengan data.")

    assert result.is_toxic is False
    assert result.score == 0.0


def test_non_toxic_english_text_is_allowed(scorer):
    result = scorer.score("Please explain the result using a simpler example.")

    assert result.is_toxic is False
    assert result.score == 0.0


def test_threshold_boundary_exactly_point_two_is_toxic(monkeypatch, scorer):
    monkeypatch.setattr(scorer, "TOXIC_TERMS", {"mild": 0.2})
    result = scorer.score("mild language")

    assert result.score == 0.2
    assert result.is_toxic is True


def test_empty_text_is_not_toxic(scorer):
    result = scorer.score("")

    assert result.is_toxic is False
    assert result.score == 0.0
    assert result.labels == []


def test_repeated_same_term_counts_once(scorer):
    result = scorer.score("bodoh bodoh bodoh")

    assert result.score == 0.25
    assert result.labels == ["bodoh"]


def test_mixed_indonesian_and_english_terms_accumulate(scorer):
    result = scorer.score("Dasar idiot dan stupid")

    assert result.score == 0.55
    assert result.labels == ["idiot", "stupid"]


def test_labels_follow_term_definition_order(scorer):
    result = scorer.score("shit anjing goblok")

    assert result.labels == ["goblok", "shit", "anjing"]


def test_threshold_attribute_is_used_for_classification(scorer):
    result = scorer.score("bodoh")

    assert scorer.threshold == 0.2
    assert result.score >= scorer.threshold
