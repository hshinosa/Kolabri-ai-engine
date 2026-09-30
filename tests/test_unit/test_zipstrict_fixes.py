"""Regression tests for zip(..., strict=True) fixes (item S10).

Guards against silent truncation when paired sequences diverge:
- vector_store.add_documents: length checks before Qdrant upsert
- batch precomputed endpoint: requests/cached values must align
- logic_listener cosine similarity: equal-length vectors required
- reranker: one score per document required, graceful fallback otherwise
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock heavier modules before imports (mirrors test_batch_routes.py)
for _mod in (
    "chromadb",
    "chromadb.config",
    "chromadb.utils",
    "hnswlib",
    "pypdf",
    "fitz",
    "docx",
    "pptx",
    "openpyxl",
    "pandas",
    "PIL",
    "motor",
    "motor.motor_asyncio",
    "redis.asyncio",
    "redis",
    "prometheus_client",
):
    sys.modules[_mod] = MagicMock()

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.batch_routes import router as batch_router
from app.services import reranker as reranker_module
from app.services.logic_listener import LogicListener
from app.services.reranker import CrossEncoderReranker
from app.services.vector_store import VectorStoreService


# ===========================================================================
# vector_store.add_documents
# ===========================================================================


def _make_store(embeddings):
    svc = VectorStoreService()
    svc._client = MagicMock()
    svc._embedding_service = MagicMock()
    svc._embedding_service.embed_texts = AsyncMock(return_value=embeddings)
    svc._initialized = True
    return svc


@pytest.mark.asyncio
async def test_add_documents_rejects_mismatched_input_lengths():
    """Misaligned documents/metadatas/ids must fail before any side effect."""
    svc = _make_store(embeddings=[[0.1, 0.2, 0.3]])

    with patch.object(
        svc, "_ensure_collection", new=AsyncMock(return_value="docs")
    ) as mock_ensure:
        with pytest.raises(ValueError) as exc_info:
            await svc.add_documents(
                documents=["doc1", "doc2"],
                metadatas=[{"page": 1}],
                ids=["id1", "id2"],
                collection_name="docs",
            )

    message = str(exc_info.value)
    assert "documents=2" in message
    assert "metadatas=1" in message
    assert "ids=2" in message
    # Fails before collection ensure / embedding / upsert.
    mock_ensure.assert_not_awaited()
    svc._embedding_service.embed_texts.assert_not_awaited()
    svc._client.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_add_documents_rejects_fewer_embeddings_than_documents():
    """A short embeddings list (provider drop/misalignment) must not silently
    truncate documents out of the upsert."""
    svc = _make_store(embeddings=[[0.1, 0.2, 0.3]])

    with patch.object(svc, "_ensure_collection", new=AsyncMock(return_value="docs")):
        with pytest.raises(ValueError) as exc_info:
            await svc.add_documents(
                documents=["doc1", "doc2"],
                metadatas=[{"page": 1}, {"page": 2}],
                ids=["id1", "id2"],
                collection_name="docs",
            )

    message = str(exc_info.value)
    assert "documents=2" in message
    assert "embeddings=1" in message
    svc._client.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_add_documents_trims_extra_embeddings():
    """Extra trailing embeddings are unusable (no document to pair with) and
    are trimmed explicitly instead of tripping strict zip."""
    svc = _make_store(embeddings=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])

    with (
        patch.object(svc, "_ensure_collection", new=AsyncMock(return_value="docs")),
        patch(
            "app.services.vector_store.PointStruct", side_effect=lambda **kw: kw
        ),
    ):
        await svc.add_documents(
            documents=["doc1"],
            metadatas=[{"page": 1}],
            ids=["id1"],
            collection_name="docs",
        )

    upsert_kwargs = svc._client.upsert.call_args.kwargs
    assert len(upsert_kwargs["points"]) == 1
    assert upsert_kwargs["points"][0]["vector"] == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_add_documents_equal_lengths_upserts_all_points():
    """Happy path: equal lengths zip strictly, one point per document."""
    svc = _make_store(embeddings=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])

    with (
        patch.object(svc, "_ensure_collection", new=AsyncMock(return_value="docs")),
        patch(
            "app.services.vector_store.PointStruct", side_effect=lambda **kw: kw
        ),
    ):
        await svc.add_documents(
            documents=["doc1", "doc2"],
            metadatas=[{"page": 1}, {"page": 2}],
            ids=["id1", "id2"],
            collection_name="docs",
        )

    upsert_kwargs = svc._client.upsert.call_args.kwargs
    assert len(upsert_kwargs["points"]) == 2
    assert upsert_kwargs["points"][0]["payload"]["document_id"] == "id1"
    assert upsert_kwargs["points"][1]["payload"]["document_id"] == "id2"
    assert upsert_kwargs["points"][1]["vector"] == [0.4, 0.5, 0.6]


# ===========================================================================
# batch precomputed endpoint
# ===========================================================================

_batch_app = FastAPI()
_batch_app.include_router(batch_router)
_batch_client = TestClient(_batch_app)

_BATCH_PAYLOAD = {
    "requests": [
        {"query": "Q1", "course_id": "c1", "request_id": "1"},
        {"query": "Q2", "course_id": "c1", "request_id": "2"},
    ]
}


@patch("app.api.batch_routes.get_llm_service")
@patch("app.api.batch_routes.get_redis_cache")
@patch("app.api.batch_routes.get_rag_pipeline")
def test_precomputed_batch_mget_short_result_raises(mock_rag, mock_redis, mock_llm):
    """If mget violates its one-value-per-key contract, the endpoint must fail
    loudly instead of silently dropping trailing requests from the response."""
    mock_llm.return_value = MagicMock()
    mock_rag.return_value = MagicMock()
    redis_cache = MagicMock()
    redis_cache.mget = AsyncMock(return_value=[{"answer": "A1"}])  # 1 value, 2 requests
    mock_redis.return_value = redis_cache

    with pytest.raises(ValueError):
        _batch_client.post("/ask/batch/precomputed", json=_BATCH_PAYLOAD)


@patch("app.api.batch_routes.get_llm_service")
@patch("app.api.batch_routes.get_redis_cache")
@patch("app.api.batch_routes.get_rag_pipeline")
def test_precomputed_batch_equal_lengths_still_succeeds(
    mock_rag, mock_redis, mock_llm
):
    """Equal-length mget result still processes every request."""
    mock_llm.return_value = MagicMock()
    mock_rag.return_value = MagicMock()
    redis_cache = MagicMock()
    redis_cache.mget = AsyncMock(return_value=[{"answer": "A1"}, None])
    mock_redis.return_value = redis_cache

    response = _batch_client.post("/ask/batch/precomputed", json=_BATCH_PAYLOAD)

    assert response.status_code == 200
    payload = response.json()
    assert payload["successful_count"] == 1
    assert payload["failed_count"] == 1
    assert [r["answer"] for r in payload["results"]] == ["A1", ""]
    assert payload["results"][1]["error"] == "Query not pre-computed"


# ===========================================================================
# logic_listener cosine similarity
# ===========================================================================


@pytest.fixture
def listener():
    return LogicListener()


def test_cosine_similarity_rejects_length_mismatch(listener):
    """Cosine of different-length vectors is undefined; must not silently
    truncate to the shorter length."""
    with pytest.raises(ValueError):
        listener._calculate_cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0])


def test_cosine_similarity_equal_lengths_still_works(listener):
    assert listener._calculate_cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert listener._calculate_cosine_similarity([2.0, 0.0], [3.0, 0.0]) == 1.0


@pytest.mark.asyncio
async def test_check_relevance_handles_dimension_mismatch_gracefully(listener):
    """If the embedding service returns different dimensions for message and
    topic, check_relevance must degrade to no-intervention, not corrupt the
    similarity score."""
    await listener.set_group_topic("group_1", "Database")

    fake_service = MagicMock()
    fake_service.get_embedding = AsyncMock(side_effect=[[1.0, 0.0], [1.0, 0.0, 0.0]])
    with patch.object(listener, "embedding_service", fake_service):
        result = await listener.check_relevance("some message", "group_1")

    assert result.should_intervene is False
    assert "Error" in result.reason
    assert listener._off_topic_counter.get("group_1") is None


# ===========================================================================
# reranker
# ===========================================================================


def _docs():
    return [
        {"id": 1, "content": "doc one"},
        {"id": 2, "content": "doc two"},
        {"id": 3, "content": "doc three"},
    ]


@pytest.mark.asyncio
async def test_rerank_score_count_mismatch_falls_back_without_dropping_docs():
    """A model returning fewer scores than documents must not silently drop
    trailing documents; strict zip trips the existing fallback path."""
    mock_model = MagicMock()
    mock_model.rerank.return_value = [0.9, 0.1]  # 2 scores for 3 documents

    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", True),
        patch.object(reranker_module, "CROSS_ENCODER_AVAILABLE", True),
    ):
        instance = CrossEncoderReranker(top_k=3)
    instance.model = mock_model
    documents = _docs()

    result = await instance.rerank("query", documents)

    # Fallback returns every document in original order — nothing truncated.
    assert result == documents
    assert instance.total_reranks == 0


@pytest.mark.asyncio
async def test_rerank_extra_scores_still_falls_back():
    """More scores than documents also violates the one-score-per-document
    contract and must not mispair scores."""
    mock_model = MagicMock()
    mock_model.rerank.return_value = [0.9, 0.1, 0.5, 0.7]  # 4 scores, 3 docs

    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", True),
        patch.object(reranker_module, "CROSS_ENCODER_AVAILABLE", True),
    ):
        instance = CrossEncoderReranker(top_k=3)
    instance.model = mock_model
    documents = _docs()

    result = await instance.rerank("query", documents)

    assert result == documents
    assert instance.total_reranks == 0


@pytest.mark.asyncio
async def test_rerank_equal_scores_ranks_normally():
    """One score per document — the contract case — still ranks correctly."""
    mock_model = MagicMock()
    mock_model.rerank.return_value = [0.1, 0.9, 0.5]

    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", True),
        patch.object(reranker_module, "CROSS_ENCODER_AVAILABLE", True),
    ):
        instance = CrossEncoderReranker(top_k=3)
    instance.model = mock_model
    documents = _docs()

    result = await instance.rerank("query", documents)

    assert [d["id"] for d in result] == [2, 3, 1]
    assert instance.total_reranks == 1
