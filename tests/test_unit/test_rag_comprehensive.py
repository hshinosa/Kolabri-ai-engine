"""Comprehensive tests for the current RAG pipeline API."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.guardrails import GuardrailAction
from app.services.rag_quality import RetrievalQualityControls
from app.services import rag as rag_module
from app.services.rag import RAGPipeline, RAGResult, get_rag_pipeline


@pytest.fixture
def mock_vector_store():
    mock = MagicMock()
    mock.search = AsyncMock(
        return_value=[
            {"content": "Test content", "metadata": {"source": "test.pdf", "page": 1}, "score": 0.85}
        ]
    )
    return mock


@pytest.fixture
def mock_llm():
    mock = MagicMock()
    mock.generate = AsyncMock(return_value=MagicMock(content="Test response", tokens_used=50, success=True, error=None))
    mock.generate_rag_response = AsyncMock(return_value=MagicMock(content="RAG response", tokens_used=100, success=True, error=None))
    mock.reframe_to_socratic = AsyncMock(return_value="Reframed response")
    return mock


@pytest.fixture
def mock_guardrails():
    mock = MagicMock()
    mock.check_input.return_value = MagicMock(
        action=GuardrailAction.ALLOW,
        message=None,
        sanitized_input=None,
        reason=None,
    )
    mock.check_output.return_value = MagicMock(
        action=GuardrailAction.ALLOW,
        message=None,
        sanitized_input=None,
    )
    return mock


@pytest.fixture
def rag_pipeline(mock_vector_store, mock_llm, mock_guardrails):
    with patch("app.services.rag.get_guardrails", return_value=mock_guardrails):
        with patch.object(rag_module.settings, "ENABLE_EFFICIENCY_GUARD", False):
            return RAGPipeline(vector_store=mock_vector_store, llm_service=mock_llm, efficiency_guard=None)


class TestRAGResult:
    def test_rag_result_success(self):
        result = RAGResult("Test answer", [{"source": "doc.pdf", "page": 1}], "Test query", 100, True, processing_time_ms=50.0)
        assert result.answer == "Test answer"
        assert result.success is True

    def test_rag_result_with_error(self):
        result = RAGResult("", [], "Test query", 0, False, error="Test error")
        assert result.error == "Test error"


class TestRAGPipeline:
    def test_init(self, mock_vector_store, mock_llm, mock_guardrails):
        with patch("app.services.rag.get_guardrails", return_value=mock_guardrails):
            pipeline = RAGPipeline(vector_store=mock_vector_store, llm_service=mock_llm, efficiency_guard=None)
        assert pipeline.vector_store is mock_vector_store
        assert pipeline.llm_service is mock_llm

    def test_init_uses_configurable_semantic_threshold(self, mock_vector_store, mock_llm, mock_guardrails):
        with patch("app.services.rag.get_guardrails", return_value=mock_guardrails), patch.object(
            rag_module.settings, "RAG_SEMANTIC_CACHE_THRESHOLD", 0.93
        ):
            pipeline = RAGPipeline(vector_store=mock_vector_store, llm_service=mock_llm, efficiency_guard=None)

        assert pipeline._semantic_threshold == 0.93

    def test_init_accepts_internal_quality_controls(self, mock_vector_store, mock_llm, mock_guardrails):
        controls = RetrievalQualityControls(
            top_k_results=4,
            similarity_threshold=0.81,
            semantic_cache_threshold=0.91,
            reranking_enabled=True,
            rerank_top_k=2,
            rerank_retrieve_k=9,
            grounding_threshold=0.55,
        )

        with patch("app.services.rag.get_guardrails", return_value=mock_guardrails):
            pipeline = RAGPipeline(
                vector_store=mock_vector_store,
                llm_service=mock_llm,
                efficiency_guard=None,
                quality_controls=controls,
            )

        assert pipeline.quality_controls is controls
        assert pipeline._semantic_threshold == 0.91
        assert pipeline._grounding_threshold == 0.55

    def test_should_retrieve(self, rag_pipeline):
        assert rag_pipeline._should_retrieve("halo") is False
        assert rag_pipeline._should_retrieve("test") is False
        assert rag_pipeline._should_retrieve("halo apa kabar") is False
        assert rag_pipeline._should_retrieve("Jelaskan tentang machine learning dan deep learning") is True

    def test_format_search_results_and_extract_sources(self, rag_pipeline):
        results = [
            {"content": "Doc 1", "metadata": {"source": "test.pdf", "page": 1, "chunk_index": 0}, "score": 0.9},
            {"content": "Doc 2", "metadata": {"source": "test.pdf", "page": 2}, "score": 0.8},
        ]
        contexts = rag_pipeline._format_search_results(results)
        assert contexts[0]["content"] == "Doc 1"
        sources = rag_pipeline._extract_sources(results)
        assert len(sources) == 1
        assert sources[0]["source"] == "test.pdf"

    @pytest.mark.asyncio
    async def test_query_no_fetch_greeting(self, rag_pipeline, mock_guardrails):
        mock_guardrails.check_input.return_value = MagicMock(action=GuardrailAction.ALLOW, sanitized_input="halo", reason=None, message=None)
        result = await rag_pipeline.query("halo")
        assert result.success is True
        assert result.answer == "Test response"

    @pytest.mark.asyncio
    async def test_query_blocked(self, rag_pipeline, mock_guardrails):
        mock_guardrails.check_input.return_value = MagicMock(action=GuardrailAction.BLOCK, message="Blocked message", sanitized_input=None, reason="blocked")
        result = await rag_pipeline.query("Kerjakan tugas saya")
        assert result.success is True
        assert result.answer == "Blocked message"

    @pytest.mark.asyncio
    async def test_query_fetch(self, rag_pipeline, mock_guardrails):
        mock_guardrails.check_input.return_value = MagicMock(action=GuardrailAction.ALLOW, sanitized_input="Jelaskan machine learning", reason=None, message=None)
        with patch("app.services.grounding_verifier.get_grounding_verifier") as mock_grounding:
            mock_grounding.return_value.verify_grounding_async = AsyncMock(
                return_value=MagicMock(is_grounded=True, grounding_ratio=1.0, ungrounded_claims=[])
            )
            result = await rag_pipeline.query("Jelaskan machine learning dan deep learning")
        assert result.success is True
        assert len(result.sources) > 0

    @pytest.mark.asyncio
    async def test_query_uses_reranker_controls_when_enabled(self, mock_vector_store, mock_llm, mock_guardrails):
        controls = RetrievalQualityControls(
            top_k_results=5,
            similarity_threshold=0.6,
            semantic_cache_threshold=0.85,
            reranking_enabled=True,
            rerank_top_k=2,
            rerank_retrieve_k=4,
            grounding_threshold=0.4,
        )
        mock_guardrails.check_input.return_value = MagicMock(action=GuardrailAction.ALLOW, sanitized_input="Jelaskan machine learning", reason=None, message=None)
        mock_vector_store.search = AsyncMock(
            return_value=[
                {"content": "Doc 1", "metadata": {"source": "a.pdf", "page": 1}, "score": 0.60},
                {"content": "Doc 2", "metadata": {"source": "b.pdf", "page": 2}, "score": 0.50},
                {"content": "Doc 3", "metadata": {"source": "c.pdf", "page": 3}, "score": 0.40},
            ]
        )
        mock_reranker = MagicMock(enabled=True, retrieve_k=4, top_k=2)
        mock_reranker.rerank = AsyncMock(
            return_value=[
                {"content": "Doc 2", "metadata": {"source": "b.pdf", "page": 2}, "score": 0.50, "rerank_score": 0.95},
                {"content": "Doc 1", "metadata": {"source": "a.pdf", "page": 1}, "score": 0.60, "rerank_score": 0.90},
            ]
        )

        with patch("app.services.rag.get_guardrails", return_value=mock_guardrails), patch.object(
            rag_module.settings, "ENABLE_EFFICIENCY_GUARD", False
        ), patch("app.services.grounding_verifier.get_grounding_verifier") as mock_grounding:
            mock_grounding.return_value.verify_grounding_async = AsyncMock(
                return_value=MagicMock(is_grounded=True, grounding_ratio=1.0, ungrounded_claims=[])
            )
            pipeline = RAGPipeline(
                vector_store=mock_vector_store,
                llm_service=mock_llm,
                efficiency_guard=None,
                reranker=mock_reranker,
                quality_controls=controls,
            )

            result = await pipeline.query("Jelaskan machine learning dan deep learning", n_results=2)

        assert result.success is True
        mock_vector_store.search.assert_awaited_once()
        assert mock_vector_store.search.await_args.kwargs["n_results"] == 4
        mock_reranker.rerank.assert_awaited_once()
        generate_kwargs = mock_llm.generate_rag_response.await_args.kwargs
        assert [ctx["metadata"]["source"] for ctx in generate_kwargs["contexts"]] == ["b.pdf", "a.pdf"]

    @pytest.mark.asyncio
    async def test_query_uses_internal_runtime_plan_resolution(self, mock_vector_store, mock_llm, mock_guardrails):
        controls = RetrievalQualityControls(
            top_k_results=5,
            similarity_threshold=0.81,
            semantic_cache_threshold=0.85,
            reranking_enabled=True,
            rerank_top_k=2,
            rerank_retrieve_k=9,
            grounding_threshold=0.4,
        )
        mock_guardrails.check_input.return_value = MagicMock(action=GuardrailAction.ALLOW, sanitized_input="Jelaskan machine learning", reason=None, message=None)
        mock_vector_store.search = AsyncMock(
            return_value=[
                {"content": "Doc 1", "metadata": {"source": "a.pdf", "page": 1}, "score": 0.9},
                {"content": "Doc 2", "metadata": {"source": "b.pdf", "page": 2}, "score": 0.8},
            ]
        )

        with patch("app.services.rag.get_guardrails", return_value=mock_guardrails), patch.object(
            rag_module.settings, "ENABLE_EFFICIENCY_GUARD", False
        ), patch("app.services.grounding_verifier.get_grounding_verifier") as mock_grounding:
            mock_grounding.return_value.verify_grounding_async = AsyncMock(
                return_value=MagicMock(is_grounded=True, grounding_ratio=1.0, ungrounded_claims=[])
            )
            pipeline = RAGPipeline(
                vector_store=mock_vector_store,
                llm_service=mock_llm,
                efficiency_guard=None,
                quality_controls=controls,
            )

            await pipeline.query("Jelaskan machine learning dan deep learning", n_results=2)

        search_kwargs = mock_vector_store.search.await_args.kwargs
        assert search_kwargs["n_results"] == 9
        assert search_kwargs["score_threshold"] == 0.81

    @pytest.mark.asyncio
    async def test_query_falls_back_to_vector_results_when_reranker_fails(self, mock_vector_store, mock_llm, mock_guardrails):
        mock_guardrails.check_input.return_value = MagicMock(action=GuardrailAction.ALLOW, sanitized_input="Jelaskan machine learning", reason=None, message=None)
        mock_vector_store.search = AsyncMock(
            return_value=[
                {"content": "Doc 1", "metadata": {"source": "a.pdf", "page": 1}, "score": 0.90},
                {"content": "Doc 2", "metadata": {"source": "b.pdf", "page": 2}, "score": 0.80},
            ]
        )
        mock_reranker = MagicMock(enabled=True, retrieve_k=4, top_k=2)
        mock_reranker.rerank = AsyncMock(side_effect=RuntimeError("reranker boom"))

        with patch("app.services.rag.get_guardrails", return_value=mock_guardrails), patch(
            "app.services.grounding_verifier.get_grounding_verifier"
        ) as mock_grounding:
            mock_grounding.return_value.verify_grounding_async = AsyncMock(
                return_value=MagicMock(is_grounded=True, grounding_ratio=1.0, ungrounded_claims=[])
            )
            pipeline = RAGPipeline(
                vector_store=mock_vector_store,
                llm_service=mock_llm,
                efficiency_guard=None,
                reranker=mock_reranker,
            )

            result = await pipeline.query("Jelaskan machine learning dan deep learning")

        assert result.success is True
        generate_kwargs = mock_llm.generate_rag_response.await_args.kwargs
        assert [ctx["metadata"]["source"] for ctx in generate_kwargs["contexts"]] == ["a.pdf", "b.pdf"]

    @pytest.mark.asyncio
    async def test_query_no_results(self, rag_pipeline, mock_guardrails, mock_vector_store):
        mock_guardrails.check_input.return_value = MagicMock(action=GuardrailAction.ALLOW, sanitized_input="Jelaskan quantum physics", reason=None, message=None)
        mock_vector_store.search = AsyncMock(return_value=[])
        result = await rag_pipeline.query("Jelaskan quantum physics yang tidak ada di dokumen")
        assert result.success is True
        assert result.sources == []

    @pytest.mark.asyncio
    async def test_query_output_guardrails(self, rag_pipeline, mock_guardrails):
        mock_guardrails.check_input.return_value = MagicMock(action=GuardrailAction.ALLOW, sanitized_input="test query panjang", reason=None, message=None)
        with patch("app.services.grounding_verifier.get_grounding_verifier") as mock_grounding:
            mock_grounding.return_value.verify_grounding_async = AsyncMock(
                return_value=MagicMock(is_grounded=True, grounding_ratio=1.0, ungrounded_claims=[])
            )

            mock_guardrails.check_output.return_value = MagicMock(action=GuardrailAction.BLOCK, message="Output blocked", sanitized_input=None)
            blocked = await rag_pipeline.query("test query yang panjang ini")
            assert blocked.scaffolding_triggered is True

            mock_guardrails.check_output.return_value = MagicMock(action=GuardrailAction.REDIRECT, message=None, sanitized_input=None)
            redirected = await rag_pipeline.query("test query yang panjang ini")
            assert redirected.scaffolding_triggered is True
            assert redirected.answer == "Reframed response"

            mock_guardrails.check_output.return_value = MagicMock(action=GuardrailAction.SANITIZE, sanitized_input="Sanitized content", message=None)
            sanitized = await rag_pipeline.query("test query yang panjang ini")
            assert sanitized.answer == "Sanitized content"

    @pytest.mark.asyncio
    async def test_query_exception(self, rag_pipeline, mock_guardrails, mock_vector_store):
        mock_guardrails.check_input.return_value = MagicMock(action=GuardrailAction.ALLOW, sanitized_input="test query panjang", reason=None, message=None)
        mock_vector_store.search = AsyncMock(side_effect=Exception("Test error"))
        result = await rag_pipeline.query("test query yang panjang")
        assert result.success is False
        assert result.error == "Test error"

    @pytest.mark.asyncio
    async def test_query_with_efficiency_guard(self, mock_vector_store, mock_llm, mock_guardrails):
        guard = MagicMock()
        guard.execute_with_caching = AsyncMock(
            return_value={
                "answer": "Test answer",
                "sources": [],
                "query": "Test query",
                "tokens_used": 50,
                "success": True,
                "processing_time_ms": 10.0,
            }
        )
        with patch("app.services.rag.get_guardrails", return_value=mock_guardrails):
            with patch.object(rag_module.settings, "ENABLE_EFFICIENCY_GUARD", True), patch.object(
                rag_module.settings, "CACHE_TTL_SECONDS", 3600
            ):
                pipeline = RAGPipeline(vector_store=mock_vector_store, llm_service=mock_llm, efficiency_guard=guard)
                result = await pipeline.query("test query")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_is_semantically_identical(self, rag_pipeline):
        rag_pipeline._last_query = "Test query similar"
        rag_pipeline._last_contexts = [{"content": "context"}]

        with patch("app.services.embeddings.get_embedding_service") as mock_get:
            embedder = MagicMock()
            embedder.get_embedding = AsyncMock(side_effect=[[0.9, 0.1], [0.89, 0.11]])
            mock_get.return_value = embedder
            assert await rag_pipeline._is_semantically_identical("Test query similar") is True

        rag_pipeline._last_query = None
        assert await rag_pipeline._is_semantically_identical("Test query") is False

        rag_pipeline._last_query = "Test"
        rag_pipeline._last_contexts = [{}]
        with patch("app.services.embeddings.get_embedding_service", side_effect=Exception("Embedding error")):
            assert await rag_pipeline._is_semantically_identical("Test") is False

    @pytest.mark.asyncio
    async def test_query_with_course_context_and_similar_questions(self, rag_pipeline, mock_guardrails, mock_vector_store):
        mock_guardrails.check_input.return_value = MagicMock(action=GuardrailAction.ALLOW, sanitized_input="test query panjang", reason=None, message=None)
        with patch("app.services.grounding_verifier.get_grounding_verifier") as mock_grounding:
            mock_grounding.return_value.verify_grounding_async = AsyncMock(
                return_value=MagicMock(is_grounded=True, grounding_ratio=1.0, ungrounded_claims=[])
            )
            result = await rag_pipeline.query_with_course_context("Test question", course_id="course123")
        assert result.success is True

        mock_vector_store.search = AsyncMock(return_value=[{"content": "Similar question 1", "metadata": {"answer": "Answer 1"}, "score": 0.9}])
        similar = await rag_pipeline.get_similar_questions("Test query")
        assert similar[0]["question"] == "Similar question 1"

        mock_vector_store.search = AsyncMock(side_effect=Exception("Error"))
        assert await rag_pipeline.get_similar_questions("Test query") == []


class TestGetRAGPipeline:
    def test_get_rag_pipeline_singleton(self):
        rag_module._rag_pipeline = None
        with patch("app.services.rag.get_vector_store", return_value=MagicMock()):
            with patch("app.services.rag.get_llm_service", return_value=MagicMock()):
                with patch("app.services.rag.get_guardrails", return_value=MagicMock()):
                    pipeline1 = get_rag_pipeline()
                    pipeline2 = get_rag_pipeline()
        assert pipeline1 is pipeline2
