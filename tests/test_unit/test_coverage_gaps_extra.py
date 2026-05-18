"""Targeted tests for remaining coverage gaps in logging, Redis cache, and RAG."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.core.guardrails import GuardrailAction, GuardrailResult


@pytest.fixture
def redis_cache_module():
    import app.core.redis_cache as module

    module.RedisCache._instance = None
    module.RedisCache._redis = None
    module._redis_cache = None
    yield module
    module.RedisCache._instance = None
    module.RedisCache._redis = None
    module._redis_cache = None


@pytest.fixture
def mock_redis_client():
    client = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.setex = AsyncMock(return_value=True)
    client.setnx = AsyncMock(return_value=True)
    client.expire = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.mget = AsyncMock(return_value=[])
    client.close = AsyncMock()
    client.info = AsyncMock(return_value={})
    client.pipeline = MagicMock(return_value=AsyncMock())

    async def empty_scan_iter(match=None):
        if False:  # pragma: no cover
            yield match

    client.scan_iter = empty_scan_iter
    return client


@pytest.fixture
def rag_pipeline_components():
    import app.services.rag as rag_module

    vector_store = MagicMock()
    vector_store.search = AsyncMock()

    llm_service = MagicMock()
    llm_service.generate = AsyncMock()
    llm_service.generate_rag_response = AsyncMock()
    llm_service.reframe_to_socratic = AsyncMock()

    guardrails = MagicMock()
    guardrails.check_input.return_value = GuardrailResult(
        action=GuardrailAction.ALLOW,
        reason="safe",
    )
    guardrails.check_output.return_value = GuardrailResult(
        action=GuardrailAction.ALLOW,
        reason="safe",
    )

    with patch("app.services.rag.get_guardrails", return_value=guardrails), patch.object(
        settings, "ENABLE_EFFICIENCY_GUARD", False
    ):
        pipeline = rag_module.RAGPipeline(
            vector_store=vector_store,
            llm_service=llm_service,
            efficiency_guard=None,
        )

    return {
        "module": rag_module,
        "pipeline": pipeline,
        "vector_store": vector_store,
        "llm_service": llm_service,
        "guardrails": guardrails,
    }


class TestLoggingCoverageGapsExtra:
    def test_setup_logging_wraps_windows_streams_without_pytest(self):
        import app.core.logging as logging_module

        fake_stdout = SimpleNamespace(buffer=MagicMock(name="stdout-buffer"))
        fake_stderr = SimpleNamespace(buffer=MagicMock(name="stderr-buffer"))
        wrapped_stdout = MagicMock(name="wrapped-stdout")
        wrapped_stderr = MagicMock(name="wrapped-stderr")
        root_logger = MagicMock()

        original_pytest_module = logging_module.sys.modules.pop("pytest", None)
        try:
            with patch.object(logging_module.sys, "platform", "win32"), patch.object(
                logging_module.sys, "stdout", fake_stdout
            ), patch.object(logging_module.sys, "stderr", fake_stderr), patch.object(
                settings, "LOG_FORMAT", "console"
            ), patch.object(settings, "LOG_LEVEL", "INFO"), patch(
                "io.TextIOWrapper", side_effect=[wrapped_stdout, wrapped_stderr]
            ) as mock_wrapper, patch("app.core.logging.structlog.configure"), patch(
                "app.core.logging.logging.StreamHandler"
            ) as mock_handler, patch("app.core.logging.logging.getLogger") as mock_get_logger:
                mock_get_logger.return_value = root_logger

                logging_module.setup_logging()

                assert logging_module.sys.stdout is wrapped_stdout
                assert logging_module.sys.stderr is wrapped_stderr
        finally:
            if original_pytest_module is not None:
                logging_module.sys.modules["pytest"] = original_pytest_module

        assert mock_wrapper.call_count == 2
        mock_handler.assert_called_once_with(wrapped_stdout)

    def test_setup_logging_skips_windows_wrapping_when_streams_have_no_buffer(self):
        import app.core.logging as logging_module

        root_logger = MagicMock()

        with patch.object(logging_module.sys, "platform", "win32"), patch.object(
            logging_module.sys, "modules", {"custom": object()}
        ), patch.object(logging_module.sys, "stdout", SimpleNamespace()), patch.object(
            logging_module.sys, "stderr", SimpleNamespace()
        ), patch.object(settings, "LOG_FORMAT", "console"), patch.object(
            settings, "LOG_LEVEL", "INFO"
        ), patch("io.TextIOWrapper") as mock_wrapper, patch(
            "app.core.logging.structlog.configure"
        ), patch("app.core.logging.logging.StreamHandler"), patch(
            "app.core.logging.logging.getLogger"
        ) as mock_get_logger:
            mock_get_logger.return_value = root_logger

            logging_module.setup_logging()

        mock_wrapper.assert_not_called()

    def test_setup_logging_skips_windows_wrapping_when_pytest_loaded(self):
        import app.core.logging as logging_module

        root_logger = MagicMock()

        with patch.object(logging_module.sys, "platform", "win32"), patch.object(
            logging_module.sys, "modules", {"pytest": object()}
        ), patch.object(logging_module.sys, "stdout", SimpleNamespace(buffer=MagicMock())), patch.object(
            logging_module.sys, "stderr", SimpleNamespace(buffer=MagicMock())
        ), patch.object(settings, "LOG_FORMAT", "console"), patch.object(
            settings, "LOG_LEVEL", "INFO"
        ), patch("io.TextIOWrapper") as mock_wrapper, patch(
            "app.core.logging.structlog.configure"
        ), patch("app.core.logging.logging.StreamHandler"), patch(
            "app.core.logging.logging.getLogger"
        ) as mock_get_logger:
            mock_get_logger.return_value = root_logger

            logging_module.setup_logging()

        mock_wrapper.assert_not_called()


class TestRedisCacheCoverageGapsExtra:
    @pytest.mark.asyncio
    async def test_initialize_creates_client_and_pings_when_missing(self, redis_cache_module, mock_redis_client):
        cache = redis_cache_module.RedisCache()

        with patch("app.core.redis_cache.redis.from_url", new=AsyncMock(return_value=mock_redis_client)) as mock_from_url:
            await cache.initialize()

        assert cache._redis is mock_redis_client
        mock_from_url.assert_awaited_once()
        mock_redis_client.ping.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_initialize_skips_connection_when_client_already_exists(self, redis_cache_module, mock_redis_client):
        cache = redis_cache_module.RedisCache()
        cache._redis = mock_redis_client

        with patch("app.core.redis_cache.redis.from_url", new=AsyncMock()) as mock_from_url:
            await cache.initialize()

        mock_from_url.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_close_closes_active_connection_and_resets_client(self, redis_cache_module, mock_redis_client):
        cache = redis_cache_module.RedisCache()
        cache._redis = mock_redis_client

        await cache.close()

        mock_redis_client.close.assert_awaited_once()
        assert cache._redis is None

    @pytest.mark.asyncio
    async def test_close_without_client_is_noop(self, redis_cache_module):
        cache = redis_cache_module.RedisCache()
        cache._redis = None

        await cache.close()

        assert cache._redis is None

    @pytest.mark.asyncio
    async def test_set_initializes_client_before_writing(self, redis_cache_module, mock_redis_client):
        cache = redis_cache_module.RedisCache()
        cache._redis = None

        async def initialize_client():
            cache._redis = mock_redis_client

        with patch.object(cache, "initialize", new=AsyncMock(side_effect=initialize_client)) as mock_initialize:
            result = await cache.set("lazy:key", {"value": 1}, ttl=42)

        assert result is True
        mock_initialize.assert_awaited_once()
        mock_redis_client.setex.assert_awaited_once_with("lazy:key", 42, json.dumps({"value": 1}))

    @pytest.mark.asyncio
    async def test_set_propagates_lazy_initialize_failure(self, redis_cache_module):
        cache = redis_cache_module.RedisCache()
        cache._redis = None

        with patch.object(cache, "initialize", new=AsyncMock(side_effect=RuntimeError("init failed"))) as mock_initialize:
            with pytest.raises(RuntimeError, match="init failed"):
                await cache.set("lazy:key", {"value": 1})

        mock_initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_or_set_returns_cached_value_after_waiting_for_lock_owner(self, redis_cache_module, mock_redis_client):
        cache = redis_cache_module.RedisCache()
        cache._redis = mock_redis_client
        cache.get = AsyncMock(side_effect=[None, {"cached": True}])
        getter = AsyncMock(return_value={"fresh": True})
        mock_redis_client.set = AsyncMock(return_value=False)

        with patch("app.core.redis_cache.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            result = await cache.get_or_set("shared:key", getter)

        assert result == {"cached": True}
        mock_sleep.assert_awaited_once_with(0.1)
        getter.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_or_set_recurses_when_lock_owner_has_not_filled_cache_yet(self, redis_cache_module, mock_redis_client):
        cache = redis_cache_module.RedisCache()
        cache._redis = mock_redis_client
        cache.get = AsyncMock(side_effect=[None, None, "retry-result"])
        getter = AsyncMock(return_value="fresh-value")
        mock_redis_client.set = AsyncMock(return_value=False)

        with patch("app.core.redis_cache.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            result = await cache.get_or_set("shared:key", getter)

        assert result == "retry-result"
        assert mock_sleep.await_count == 1
        assert cache.get.await_count == 3
        getter.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_or_set_falls_back_to_getter_when_lock_operation_raises(self, redis_cache_module, mock_redis_client):
        cache = redis_cache_module.RedisCache()
        cache._redis = mock_redis_client
        cache.get = AsyncMock(return_value=None)
        getter = AsyncMock(return_value="fallback-value")
        mock_redis_client.set = AsyncMock(side_effect=RuntimeError("redis down"))

        result = await cache.get_or_set("shared:key", getter)

        assert result == "fallback-value"
        getter.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clear_pattern_deletes_keys_when_matches_exist(self, redis_cache_module, mock_redis_client):
        cache = redis_cache_module.RedisCache()
        cache._redis = mock_redis_client

        async def scan_iter(match=None):
            for key in ["match:1", "match:2"]:
                yield key

        mock_redis_client.scan_iter = scan_iter

        deleted = await cache.clear_pattern("match:*")

        assert deleted == 2
        mock_redis_client.delete.assert_awaited_once_with("match:1", "match:2")

    @pytest.mark.asyncio
    async def test_clear_pattern_returns_zero_without_matches(self, redis_cache_module, mock_redis_client):
        cache = redis_cache_module.RedisCache()
        cache._redis = mock_redis_client

        async def scan_iter(match=None):
            if False:  # pragma: no cover
                yield match

        mock_redis_client.scan_iter = scan_iter

        deleted = await cache.clear_pattern("empty:*")

        assert deleted == 0
        mock_redis_client.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_redis_cache_initializes_singleton_once(self, redis_cache_module):
        created_cache = redis_cache_module.RedisCache()

        with patch.object(redis_cache_module, "RedisCache", return_value=created_cache) as mock_cache_cls, patch.object(
            created_cache, "initialize", new=AsyncMock()
        ) as mock_initialize:
            cache_one = await redis_cache_module.get_redis_cache()
            cache_two = await redis_cache_module.get_redis_cache()

        assert cache_one is created_cache
        assert cache_two is created_cache
        mock_cache_cls.assert_called_once_with()
        mock_initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_redis_cache_reuses_existing_singleton(self, redis_cache_module):
        existing_cache = MagicMock()
        redis_cache_module._redis_cache = existing_cache

        result = await redis_cache_module.get_redis_cache()

        assert result is existing_cache


class TestRagCoverageGapsExtra:
    def test_should_retrieve_skips_short_greeting_prefix_queries(self, rag_pipeline_components):
        pipeline = rag_pipeline_components["pipeline"]

        assert pipeline._should_retrieve("halo teman kelas") is False

    def test_should_retrieve_fetches_long_greeting_prefix_queries(self, rag_pipeline_components):
        pipeline = rag_pipeline_components["pipeline"]

        assert pipeline._should_retrieve("halo teman bisa jelaskan materi redis cache") is True

    def test_should_retrieve_skips_exact_greeting_patterns(self, rag_pipeline_components):
        pipeline = rag_pipeline_components["pipeline"]

        assert pipeline._should_retrieve("thanks") is False

    def test_should_retrieve_skips_short_queries(self, rag_pipeline_components):
        pipeline = rag_pipeline_components["pipeline"]

        assert pipeline._should_retrieve("materi redis") is False

    @pytest.mark.asyncio
    async def test_query_uses_semantic_cache_contexts_without_vector_search(self, rag_pipeline_components):
        pipeline = rag_pipeline_components["pipeline"]
        vector_store = rag_pipeline_components["vector_store"]
        llm_service = rag_pipeline_components["llm_service"]
        guardrails = rag_pipeline_components["guardrails"]

        pipeline._last_contexts = [{"content": "cached context", "metadata": {"source": "cache"}, "score": 0.9}]
        llm_service.generate_rag_response.return_value = SimpleNamespace(
            content="Cached answer",
            tokens_used=17,
            success=True,
            error=None,
        )
        grounded = SimpleNamespace(is_grounded=True, grounding_ratio=0.95, ungrounded_claims=[])
        verifier = MagicMock(verify_grounding_async=AsyncMock(return_value=grounded))

        with patch.object(pipeline, "_is_semantically_identical", new=AsyncMock(return_value=True)), patch(
            "app.services.grounding_verifier.get_grounding_verifier",
            return_value=verifier,
        ):
            result = await pipeline.query("Jelaskan redis cache")

        assert result.answer == "Cached answer"
        assert result.success is True
        assert result.sources == []
        vector_store.search.assert_not_awaited()
        llm_service.generate_rag_response.assert_awaited_once()
        guardrails.check_output.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_grounding_failure_returns_scaffolded_response(self, rag_pipeline_components):
        pipeline = rag_pipeline_components["pipeline"]
        vector_store = rag_pipeline_components["vector_store"]
        llm_service = rag_pipeline_components["llm_service"]

        vector_store.search.return_value = [
            {
                "content": "Redis cache menyimpan hasil query",
                "metadata": {"source": "redis.pdf", "page": 3},
                "score": 0.88,
            }
        ]
        llm_service.generate_rag_response.return_value = SimpleNamespace(
            content="Jawaban spekulatif",
            tokens_used=29,
            success=True,
            error=None,
        )
        ungrounded = SimpleNamespace(
            is_grounded=False,
            grounding_ratio=0.2,
            ungrounded_claims=["klaim 1", "klaim 2", "klaim 3"],
        )
        verifier = MagicMock(verify_grounding_async=AsyncMock(return_value=ungrounded))

        with patch.object(pipeline, "_is_semantically_identical", new=AsyncMock(return_value=False)), patch(
            "app.services.grounding_verifier.get_grounding_verifier",
            return_value=verifier,
        ):
            result = await pipeline.query("Jelaskan fungsi Redis cache")

        assert result.success is True
        assert result.scaffolding_triggered is True
        assert result.answer == "Jawaban tidak dapat diberikan tanpa berspekulasi di luar materi yang tersedia."
        assert result.tokens_used == 29
        assert result.sources == [
            {
                "source": "redis.pdf",
                "page": 3,
                "chunk_index": None,
                "relevance_score": 0.88,
            }
        ]

    @pytest.mark.asyncio
    async def test_query_grounding_failure_skips_output_guardrails(self, rag_pipeline_components):
        pipeline = rag_pipeline_components["pipeline"]
        vector_store = rag_pipeline_components["vector_store"]
        llm_service = rag_pipeline_components["llm_service"]
        guardrails = rag_pipeline_components["guardrails"]

        vector_store.search.return_value = [
            {
                "content": "Dokumen relevan",
                "metadata": {"source": "rag.pdf"},
                "score": 0.81,
            }
        ]
        llm_service.generate_rag_response.return_value = SimpleNamespace(
            content="Jawaban model",
            tokens_used=11,
            success=True,
            error=None,
        )
        verifier = MagicMock(
            verify_grounding=MagicMock(
                return_value=SimpleNamespace(
                    is_grounded=False,
                    grounding_ratio=0.4,
                    ungrounded_claims=["klaim"],
                )
            )
        )

        with patch.object(pipeline, "_is_semantically_identical", new=AsyncMock(return_value=False)), patch(
            "app.services.grounding_verifier.get_grounding_verifier",
            return_value=verifier,
        ):
            await pipeline.query("Butuh jawaban berbasis dokumen")

        guardrails.check_output.assert_not_called()
