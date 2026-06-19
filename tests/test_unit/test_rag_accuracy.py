import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.grounding_verifier import GroundingResult, GroundingVerifier


def _normalize_tokens(text: str) -> set[str]:
    return set(re.findall(r"\b\w+\b", text.lower()))


def _keyword_overlap_ratio(left: str, right: str) -> float:
    left_tokens = _normalize_tokens(left)
    right_tokens = _normalize_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens)


def _extract_claims(text: str) -> list[str]:
    return [segment.strip() for segment in re.split(r"[.!?]+", text) if len(segment.strip()) > 10]


def compute_faithfulness_score(response: str, contexts: list[str], threshold: float = 0.5) -> float:
    claims = _extract_claims(response)
    if not claims:
        return 1.0

    grounded_claims = 0
    for claim in claims:
        best_overlap = max((_keyword_overlap_ratio(claim, context) for context in contexts), default=0.0)
        if best_overlap >= threshold:
            grounded_claims += 1

    return grounded_claims / len(claims)


def compute_context_relevance_score(query: str, contexts: list[str], threshold: float = 0.25) -> float:
    if not contexts:
        return 0.0

    relevant_contexts = 0
    for context in contexts:
        if _keyword_overlap_ratio(query, context) >= threshold:
            relevant_contexts += 1

    return relevant_contexts / len(contexts)


def compute_context_precision_score(query: str, contexts: list[str], threshold: float = 0.25) -> float:
    relevant_flags = [_keyword_overlap_ratio(query, context) >= threshold for context in contexts]
    total_relevant = sum(relevant_flags)
    if total_relevant == 0:
        return 0.0

    relevant_seen = 0
    precision_sum = 0.0
    for rank, is_relevant in enumerate(relevant_flags, start=1):
        if is_relevant:
            relevant_seen += 1
            precision_sum += relevant_seen / rank

    return precision_sum / total_relevant


def compute_context_recall_score(expected_facts: list[str], contexts: list[str], threshold: float = 0.4) -> float:
    if not expected_facts:
        return 1.0

    matched = 0
    for fact in expected_facts:
        best_overlap = max((_keyword_overlap_ratio(fact, context) for context in contexts), default=0.0)
        if best_overlap >= threshold:
            matched += 1

    return matched / len(expected_facts)


FULLY_GROUNDED_CONTEXTS = [
    "Machine learning is a branch of artificial intelligence that learns patterns from data.",
    "Supervised learning uses labeled examples to train predictive models.",
]


PARTIALLY_GROUNDED_CONTEXTS = [
    "Machine learning learns patterns from historical data.",
    "Classification predicts a label for each input example.",
]


UNGROUNDED_CONTEXTS = [
    "Photosynthesis converts sunlight into chemical energy in plants.",
    "Volcanoes release magma and ash during eruptions.",
]


RELEVANT_QUERY = "how does machine learning use labeled data"


EXPECTED_FACTS = [
    "machine learning learns patterns from data",
    "supervised learning uses labeled data",
    "models make predictions from examples",
]


def test_normalize_tokens_lowercases_and_splits_words():
    assert _normalize_tokens("Machine Learning, DATA!") == {"machine", "learning", "data"}


def test_keyword_overlap_ratio_is_one_for_identical_keywords():
    assert _keyword_overlap_ratio("machine learning data", "machine learning data") == 1.0


def test_keyword_overlap_ratio_is_zero_for_disjoint_text():
    assert _keyword_overlap_ratio("machine learning", "volcano eruption") == 0.0


def test_extract_claims_splits_long_sentences_only():
    claims = _extract_claims("Short. Machine learning learns from data. Models predict labels!")
    assert claims == ["Machine learning learns from data", "Models predict labels"]


def test_faithfulness_helper_returns_one_for_no_claims():
    assert compute_faithfulness_score("", FULLY_GROUNDED_CONTEXTS) == 1.0


def test_faithfulness_fully_grounded_score_is_one():
    response = (
        "Machine learning is a branch of artificial intelligence that learns patterns from data. "
        "Supervised learning uses labeled examples to train predictive models."
    )
    assert compute_faithfulness_score(response, FULLY_GROUNDED_CONTEXTS) == 1.0


def test_faithfulness_partially_grounded_score_is_between_zero_and_one():
    response = (
        "Machine learning learns patterns from historical data. "
        "Neural implants can read human dreams perfectly."
    )
    score = compute_faithfulness_score(response, PARTIALLY_GROUNDED_CONTEXTS)
    assert 0.0 < score < 1.0


def test_faithfulness_completely_ungrounded_score_is_zero():
    response = "Space elevators are already operating commercially in Jakarta."
    assert compute_faithfulness_score(response, UNGROUNDED_CONTEXTS) == 0.0


@pytest.mark.parametrize(
    ("response", "contexts", "expected"),
    [
        (
            "Machine learning learns patterns from data.",
            ["Machine learning learns patterns from data."],
            1.0,
        ),
        (
            "Machine learning learns patterns from data. Quantum whales write code.",
            ["Machine learning learns patterns from data."],
            0.5,
        ),
        (
            "Quantum whales write code underwater.",
            ["Machine learning learns patterns from data."],
            0.0,
        ),
    ],
)
def test_faithfulness_helper_parametrized_cases(response, contexts, expected):
    assert compute_faithfulness_score(response, contexts) == expected


def test_context_relevance_highly_relevant_contexts_have_high_score():
    contexts = [
        "Machine learning uses labeled data to train models.",
        "Labeled examples help supervised learning classify inputs.",
    ]
    score = compute_context_relevance_score(RELEVANT_QUERY, contexts)
    assert score == 1.0


def test_context_relevance_irrelevant_contexts_have_low_score():
    contexts = [
        "Volcano eruptions release lava and ash.",
        "Plant cells use chlorophyll for photosynthesis.",
    ]
    assert compute_context_relevance_score(RELEVANT_QUERY, contexts) == 0.0


def test_context_relevance_mixed_contexts_have_medium_score():
    contexts = [
        "Machine learning uses labeled data to train models.",
        "Volcano eruptions release lava and ash.",
    ]
    score = compute_context_relevance_score(RELEVANT_QUERY, contexts)
    assert score == 0.5


def test_context_relevance_returns_zero_without_contexts():
    assert compute_context_relevance_score(RELEVANT_QUERY, []) == 0.0


@pytest.mark.parametrize(
    ("query", "contexts", "expected"),
    [
        (
            "machine learning labeled data",
            ["machine learning uses labeled data", "supervised learning trains classifiers"],
            1.0,
        ),
        (
            "machine learning labeled data",
            ["machine learning uses labeled data", "volcano magma eruption"],
            0.5,
        ),
        (
            "machine learning labeled data",
            ["volcano magma eruption", "ocean tides and coral reefs"],
            0.0,
        ),
    ],
)
def test_context_relevance_helper_parametrized_cases(query, contexts, expected):
    assert compute_context_relevance_score(query, contexts) == expected


def test_context_precision_perfect_ranking_is_one():
    contexts = [
        "Machine learning uses labeled data.",
        "Supervised learning trains prediction models.",
        "Volcanoes erupt explosively.",
    ]
    assert compute_context_precision_score(RELEVANT_QUERY, contexts) == 1.0


def test_context_precision_worst_ranking_is_zero_point_five_for_single_late_hit():
    contexts = [
        "Volcanoes erupt explosively.",
        "Machine learning uses labeled data.",
    ]
    assert compute_context_precision_score(RELEVANT_QUERY, contexts) == 0.5


def test_context_precision_multiple_relevant_items_late_reduces_score():
    contexts = [
        "Photosynthesis occurs in chloroplasts.",
        "Machine learning uses labeled data.",
        "Supervised learning trains predictive models.",
    ]
    score = compute_context_precision_score(RELEVANT_QUERY, contexts)
    assert 0.0 < score < 1.0


def test_context_precision_no_relevant_contexts_is_zero():
    assert compute_context_precision_score(RELEVANT_QUERY, UNGROUNDED_CONTEXTS) == 0.0


@pytest.mark.parametrize(
    ("contexts", "expected"),
    [
        (["machine learning labeled data", "supervised learning models"], 1.0),
        (["volcano magma eruption", "machine learning labeled data"], 0.5),
        (["volcano magma eruption", "plant chlorophyll sunlight"], 0.0),
    ],
)
def test_context_precision_helper_parametrized_cases(contexts, expected):
    assert compute_context_precision_score(RELEVANT_QUERY, contexts) == expected


def test_context_recall_full_recall_is_one():
    contexts = [
        "Machine learning learns patterns from data and models make predictions from examples.",
        "Supervised learning uses labeled data for training.",
    ]
    assert compute_context_recall_score(EXPECTED_FACTS, contexts) == 1.0


def test_context_recall_partial_recall_is_between_zero_and_one():
    contexts = ["Machine learning learns patterns from data."]
    score = compute_context_recall_score(EXPECTED_FACTS, contexts)
    assert 0.0 < score < 1.0


def test_context_recall_no_recall_is_zero():
    assert compute_context_recall_score(EXPECTED_FACTS, UNGROUNDED_CONTEXTS) == 0.0


def test_context_recall_no_expected_facts_returns_one():
    assert compute_context_recall_score([], FULLY_GROUNDED_CONTEXTS) == 1.0


@pytest.mark.parametrize(
    ("expected_facts", "contexts", "expected"),
    [
        (["alpha beta"], ["alpha beta"], 1.0),
        (["alpha beta", "gamma delta"], ["alpha beta"], 0.5),
        (["alpha beta"], ["omega theta"], 0.0),
    ],
)
def test_context_recall_helper_parametrized_cases(expected_facts, contexts, expected):
    assert compute_context_recall_score(expected_facts, contexts) == expected


def test_metric_helpers_keep_scores_within_zero_and_one():
    faithfulness = compute_faithfulness_score("alpha beta. gamma delta.", ["alpha beta"])
    relevance = compute_context_relevance_score("alpha beta", ["alpha beta", "omega theta"])
    precision = compute_context_precision_score("alpha beta", ["alpha beta", "omega theta"])
    recall = compute_context_recall_score(["alpha beta", "gamma delta"], ["alpha beta"])
    for score in (faithfulness, relevance, precision, recall):
        assert 0.0 <= score <= 1.0


def test_metric_helpers_distinguish_medium_scores_consistently():
    assert (
        compute_faithfulness_score(
            "alpha beta epsilon zeta. gamma lambda mu nu.",
            ["alpha beta epsilon zeta"],
        )
        == 0.5
    )
    assert compute_context_relevance_score("alpha beta", ["alpha beta", "omega theta"]) == 0.5
    assert compute_context_recall_score(["alpha beta", "gamma delta"], ["alpha beta"]) == 0.5


def test_grounding_verifier_sync_returns_grounded_result_for_supported_response():
    verifier = GroundingVerifier()
    response = "Machine learning learns patterns from data"
    documents = [{"content": "Machine learning learns patterns from data in historical examples"}]

    result = verifier.verify_grounding(response, documents, threshold=0.5, claim_threshold=0.5)

    assert isinstance(result, GroundingResult)
    assert result.is_grounded is True
    assert result.grounding_ratio == 1.0
    assert result.ungrounded_claims == []


def test_grounding_verifier_sync_returns_partial_grounding_for_mixed_claims():
    verifier = GroundingVerifier()
    response = "Machine learning learns patterns from data. Quantum whales build lunar elevators."
    documents = [{"content": "Machine learning learns patterns from data using examples."}]

    result = verifier.verify_grounding(response, documents, threshold=0.5, claim_threshold=0.5)

    assert result.grounding_ratio == 0.5
    assert result.is_grounded is True
    assert len(result.grounded_claims) == 1
    assert len(result.ungrounded_claims) == 1


def test_grounding_verifier_sync_returns_zero_for_unsupported_response():
    verifier = GroundingVerifier()
    response = "Quantum whales build lunar elevators."
    documents = [{"content": "Machine learning learns patterns from data."}]

    result = verifier.verify_grounding(response, documents, threshold=0.7, claim_threshold=0.5)

    assert result.is_grounded is False
    assert result.grounding_ratio == 0.0
    assert result.ungrounded_claims == ["Quantum whales build lunar elevators."]


def test_grounding_verifier_sync_accepts_page_content_documents():
    verifier = GroundingVerifier()
    result = verifier.verify_grounding(
        "Models make predictions from examples",
        [{"page_content": "Models make predictions from examples in production systems"}],
        threshold=0.5,
        claim_threshold=0.5,
    )
    assert result.is_grounded is True


def test_grounding_verifier_sync_empty_documents_fail_fast():
    verifier = GroundingVerifier()
    result = verifier.verify_grounding("Useful grounded answer", [])
    assert result.is_grounded is False
    assert result.grounding_ratio == 0.0
    assert result.total_claims == 1


def test_grounding_verifier_sync_non_factual_response_returns_default_claim():
    verifier = GroundingVerifier()
    claims = verifier._extract_claims("Maaf saya tidak tahu jawabannya. Silakan cek sumber lain sekarang")
    assert claims == ["Maaf saya tidak tahu jawabannya"]


def test_grounding_verifier_sync_confidence_increases_with_large_margin():
    verifier = GroundingVerifier()
    result = verifier.verify_grounding(
        "machine learning labeled data predictive models",
        [{"content": "machine learning labeled data predictive models"}],
        threshold=0.2,
        claim_threshold=0.2,
    )
    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_grounding_verifier_async_verify_with_mocked_embeddings_returns_grounded_result():
    embedding_service = MagicMock()
    embedding_service.get_embedding = AsyncMock(side_effect=[[1.0, 0.0], [1.0, 0.0]])
    verifier = GroundingVerifier(embedding_service=embedding_service)

    with patch("app.services.grounding_verifier.np.dot", return_value=1.0), patch(
        "app.services.grounding_verifier.np.linalg.norm",
        side_effect=[1.0, 1.0],
    ):
        result = await verifier.verify_grounding_async(
            "machine learning learns from data",
            [{"content": "machine learning learns from data"}],
        )

    assert result.is_grounded is True
    assert result.grounding_ratio == 1.0
    assert embedding_service.get_embedding.await_count == 1  # PERF-AI-05: cached for identical text


@pytest.mark.asyncio
async def test_grounding_verifier_async_verify_with_mocked_embeddings_returns_partial_result():
    verifier = GroundingVerifier(embedding_service=MagicMock())

    with patch.object(verifier, "_extract_claims", return_value=["claim one", "claim two"]), patch.object(
        verifier,
        "_compute_similarity_async",
        new=AsyncMock(side_effect=[0.8, 0.2]),
    ):
        result = await verifier.verify_grounding_async(
            "response",
            [{"content": "doc"}],
            threshold=0.5,
            claim_threshold=0.5,
        )

    assert result.is_grounded is True
    assert result.grounding_ratio == 0.5
    assert result.grounded_claims == ["claim one"]
    assert result.ungrounded_claims == ["claim two"]


@pytest.mark.asyncio
async def test_grounding_verifier_async_verify_with_mocked_embeddings_returns_ungrounded_result():
    verifier = GroundingVerifier(embedding_service=MagicMock())

    with patch.object(verifier, "_extract_claims", return_value=["claim one"]), patch.object(
        verifier,
        "_compute_similarity_async",
        new=AsyncMock(return_value=0.1),
    ):
        result = await verifier.verify_grounding_async(
            "response",
            [{"content": "doc"}],
            threshold=0.7,
            claim_threshold=0.5,
        )

    assert result.is_grounded is False
    assert result.grounding_ratio == 0.0
    assert result.ungrounded_claims == ["claim one"]


@pytest.mark.asyncio
async def test_grounding_verifier_async_falls_back_to_token_similarity_when_embeddings_fail():
    embedding_service = MagicMock()
    embedding_service.get_embedding = AsyncMock(side_effect=RuntimeError("embedding boom"))
    verifier = GroundingVerifier(embedding_service=embedding_service)

    result = await verifier.verify_grounding_async(
        "machine learning learns patterns from data",
        [{"content": "machine learning learns patterns from data"}],
        threshold=0.5,
        claim_threshold=0.5,
    )

    assert result.is_grounded is True
    assert result.grounding_ratio == 1.0


@pytest.mark.asyncio
async def test_grounding_verifier_async_uses_best_similarity_across_multiple_documents():
    verifier = GroundingVerifier(embedding_service=MagicMock())

    with patch.object(verifier, "_extract_claims", return_value=["claim one"]), \
         patch.object(verifier, "_compute_similarity", return_value=0.8), \
         patch.object(
        verifier,
        "_compute_similarity_async",
        new=AsyncMock(side_effect=[0.1, 0.3, 0.9]),
    ) as similarity_mock:
        result = await verifier.verify_grounding_async(
            "response",
            [{"content": "doc 1"}, {"content": "doc 2"}, {"content": "doc 3"}],
            claim_threshold=0.8,
        )

    assert result.is_grounded is True
    assert result.grounded_claims == ["claim one"]
    assert similarity_mock.await_count == 3


@pytest.mark.asyncio
async def test_grounding_verifier_async_supports_page_content_input():
    verifier = GroundingVerifier(embedding_service=MagicMock())

    with patch.object(verifier, "_extract_claims", return_value=["claim one"]), patch.object(
        verifier,
        "_compute_similarity_async",
        new=AsyncMock(return_value=0.9),
    ):
        result = await verifier.verify_grounding_async(
            "response",
            [{"page_content": "claim one"}],
            claim_threshold=0.8,
        )

    assert result.is_grounded is True


@pytest.mark.asyncio
async def test_grounding_verifier_async_handles_empty_documents():
    verifier = GroundingVerifier(embedding_service=MagicMock())
    result = await verifier.verify_grounding_async("response text", [])
    assert result.is_grounded is False
    assert result.total_claims == 1


@pytest.mark.asyncio
async def test_grounding_verifier_async_returns_no_claims_success_when_claim_extractor_empty():
    verifier = GroundingVerifier(embedding_service=MagicMock())
    with patch.object(verifier, "_extract_claims", return_value=[]):
        result = await verifier.verify_grounding_async("", [{"content": "doc"}])
    assert result.is_grounded is True
    assert result.total_claims == 0


@pytest.mark.asyncio
async def test_grounding_verifier_async_confidence_is_capped_at_one():
    verifier = GroundingVerifier(embedding_service=MagicMock())
    with patch.object(verifier, "_extract_claims", return_value=["claim one"]), patch.object(
        verifier,
        "_compute_similarity_async",
        new=AsyncMock(return_value=1.0),
    ):
        result = await verifier.verify_grounding_async(
            "response",
            [{"content": "doc"}],
            threshold=0.1,
            claim_threshold=0.1,
        )
    assert result.confidence == 1.0
