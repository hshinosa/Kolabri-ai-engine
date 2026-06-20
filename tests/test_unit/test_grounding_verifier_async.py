import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import grounding_verifier
from app.services.grounding_verifier import GroundingResult, GroundingVerifier, get_grounding_verifier


@pytest.mark.asyncio
async def test_compute_similarity_async_returns_cosine_similarity():
    embedding_service = MagicMock()
    embedding_service.get_embedding = AsyncMock(side_effect=[[1.0, 0.0], [1.0, 1.0]])
    verifier = GroundingVerifier(embedding_service=embedding_service)

    with patch.object(grounding_verifier.np, "dot", return_value=1.0), patch.object(
        grounding_verifier.np.linalg,
        "norm",
        side_effect=[1.0, math.sqrt(2)],
    ):
        similarity = await verifier._compute_similarity_async("alpha", "beta")

    assert similarity == pytest.approx(1 / math.sqrt(2))
    assert embedding_service.get_embedding.await_count == 2


@pytest.mark.asyncio
async def test_compute_similarity_async_falls_back_when_embedding_fails():
    embedding_service = MagicMock()
    embedding_service.get_embedding = AsyncMock(side_effect=RuntimeError("boom"))
    verifier = GroundingVerifier(embedding_service=embedding_service)

    with patch.object(verifier, "_compute_similarity", return_value=0.42) as fallback:
        similarity = await verifier._compute_similarity_async("claim text", "doc text")

    assert similarity == 0.42
    fallback.assert_called_once_with("claim text", "doc text")


def test_embedding_service_property_uses_lazy_loader_once():
    verifier = GroundingVerifier()
    mock_service = MagicMock()

    with patch("app.services.embeddings.get_embedding_service", return_value=mock_service) as loader:
        first = verifier.embedding_service
        second = verifier.embedding_service

    assert first is mock_service
    assert second is mock_service
    loader.assert_called_once()


@pytest.mark.asyncio
async def test_verify_grounding_async_returns_failure_when_documents_empty():
    verifier = GroundingVerifier(embedding_service=MagicMock())

    result = await verifier.verify_grounding_async("Jawaban penting tentang sistem.", [])

    assert isinstance(result, GroundingResult)
    assert result.is_grounded is False
    assert result.grounding_ratio == 0.0
    assert result.total_claims == 1
    assert result.ungrounded_claims == ["Jawaban penting tentang sistem."]


@pytest.mark.asyncio
async def test_verify_grounding_async_returns_success_when_no_claims():
    verifier = GroundingVerifier(embedding_service=MagicMock())

    with patch.object(verifier, "_extract_claims", return_value=[]):
        result = await verifier.verify_grounding_async("", [{"content": "dokumen"}])

    assert result.is_grounded is True
    assert result.grounding_ratio == 1.0
    assert result.confidence == 0.5
    assert result.total_claims == 0


@pytest.mark.asyncio
async def test_verify_grounding_async_marks_all_claims_grounded():
    verifier = GroundingVerifier(embedding_service=MagicMock())
    response = "Claim satu. Claim dua."
    documents = [{"content": "doc satu"}, {"content": "doc dua"}]

    with patch.object(verifier, "_extract_claims", return_value=["Claim satu", "Claim dua"]), patch.object(
        verifier,
        "_compute_similarity_async",
        new=AsyncMock(side_effect=[0.9, 0.8, 0.85, 0.95]),
    ) as similarity_mock:
        result = await verifier.verify_grounding_async(response, documents)

    assert result.is_grounded is True
    assert result.grounding_ratio == 1.0
    assert result.grounded_claims == ["Claim satu", "Claim dua"]
    assert result.ungrounded_claims == []
    assert similarity_mock.await_count == 4


@pytest.mark.asyncio
async def test_verify_grounding_async_marks_claims_ungrounded_below_threshold():
    # Mock embedding service to have embed_async attribute so async path is used
    embedding_service = MagicMock()
    embedding_service.embed_async = AsyncMock()
    verifier = GroundingVerifier(embedding_service=embedding_service)
    documents = [{"content": "doc satu"}, {"content": "doc dua"}]

    with patch.object(verifier, "_extract_claims", return_value=["Claim satu", "Claim dua"]), \
         patch.object(verifier, "_compute_similarity_async", new=AsyncMock(return_value=0.00001)), \
         patch.object(verifier, "_compute_similarity", return_value=0.0):
        result = await verifier.verify_grounding_async("response", documents)

    assert result.is_grounded is False
    assert result.grounding_ratio == 0.0
    assert result.grounded_claims == []
    assert result.ungrounded_claims == ["Claim satu", "Claim dua"]


@pytest.mark.asyncio
async def test_verify_grounding_async_supports_page_content_documents():
    verifier = GroundingVerifier(embedding_service=MagicMock())
    documents = [{"page_content": "referensi halaman"}]

    with patch.object(verifier, "_extract_claims", return_value=["referensi halaman"]), patch.object(
        verifier,
        "_compute_similarity_async",
        new=AsyncMock(return_value=0.9),
    ) as similarity_mock:
        result = await verifier.verify_grounding_async("response", documents)

    assert result.is_grounded is True
    assert result.grounded_claims == ["referensi halaman"]
    similarity_mock.assert_awaited_once_with("referensi halaman", "referensi halaman")


@pytest.mark.asyncio
async def test_verify_grounding_async_honors_custom_thresholds_for_partial_grounding():
    verifier = GroundingVerifier(embedding_service=MagicMock())
    documents = [{"content": "doc"}]

    with patch.object(verifier, "_extract_claims", return_value=["claim-1", "claim-2"]), \
         patch.object(verifier, "_compute_similarity", return_value=0.5), \
         patch.object(
        verifier,
        "_compute_similarity_async",
        new=AsyncMock(side_effect=[0.7, 0.2]),
    ):
        result = await verifier.verify_grounding_async(
            "response",
            documents,
            threshold=0.5,
            claim_threshold=0.5,
        )

    assert result.is_grounded is True
    assert result.grounding_ratio == 0.5
    assert result.grounded_claims == ["claim-1"]
    assert result.ungrounded_claims == ["claim-2"]


@pytest.mark.asyncio
async def test_verify_grounding_async_confidence_is_capped_at_one():
    verifier = GroundingVerifier(embedding_service=MagicMock())

    with patch.object(verifier, "_extract_claims", return_value=["claim"]), \
         patch.object(verifier, "_compute_similarity", return_value=1.0), \
         patch.object(
        verifier,
        "_compute_similarity_async",
        new=AsyncMock(return_value=1.0),
    ):
        result = await verifier.verify_grounding_async("response", [{"content": "doc"}], threshold=0.1)

    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_verify_grounding_async_uses_max_similarity_across_documents():
    verifier = GroundingVerifier(embedding_service=MagicMock())
    documents = [{"content": "doc-1"}, {"content": "doc-2"}, {"content": "doc-3"}]

    with patch.object(verifier, "_extract_claims", return_value=["claim"]), \
         patch.object(verifier, "_compute_similarity", return_value=0.8), \
         patch.object(
        verifier,
        "_compute_similarity_async",
        new=AsyncMock(side_effect=[0.1, 0.81, 0.3]),
    ):
        result = await verifier.verify_grounding_async("response", documents, claim_threshold=0.8)

    assert result.is_grounded is True
    assert result.grounded_claims == ["claim"]


def test_get_grounding_verifier_returns_singleton_instance():
    grounding_verifier._grounding_verifier = None

    first = get_grounding_verifier()
    second = get_grounding_verifier()

    assert isinstance(first, GroundingVerifier)
    assert first is second
