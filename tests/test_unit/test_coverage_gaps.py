"""Tests targeting specific uncovered lines to push coverage above 98%."""
import sys
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from io import StringIO


class TestLoggingWindowsBranch:
    def test_windows_encoding_fix(self):
        import app.core.logging as logging_module
        
        with patch.object(sys, 'platform', 'win32'), \
             patch.dict(sys.modules, {'pytest': None}):
            logging_module.setup_logging()

    def test_non_windows_skips_encoding(self):
        import app.core.logging as logging_module
        with patch.object(sys, 'platform', 'linux'):
            logging_module.setup_logging()


class TestLLMServiceClose:
    @pytest.mark.asyncio
    async def test_close_llm_service(self):
        import app.services.llm as llm_module
        
        mock_service = MagicMock()
        mock_service.close = AsyncMock()
        llm_module._llm_service = mock_service
        
        await llm_module.close_llm_service()
        
        mock_service.close.assert_called_once()
        assert llm_module._llm_service is None
    
    @pytest.mark.asyncio
    async def test_close_llm_service_when_none(self):
        import app.services.llm as llm_module
        llm_module._llm_service = None
        
        await llm_module.close_llm_service()
        assert llm_module._llm_service is None


class TestRAGSemanticIdentical:
    @pytest.mark.asyncio
    async def test_semantic_identical_no_last_query(self):
        from app.services.rag import RAGPipeline
        
        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline._last_query = None
        pipeline._last_contexts = None
        
        result = await pipeline._is_semantically_identical("test")
        assert result is False

    @pytest.mark.asyncio
    async def test_semantic_identical_zero_vector(self):
        from app.services.rag import RAGPipeline
        
        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline._last_query = "previous query"
        pipeline._last_contexts = [{"content": "ctx"}]
        pipeline._semantic_threshold = 0.85
        
        mock_embedder = MagicMock()
        mock_embedder.get_embedding = AsyncMock(return_value=[0.0, 0.0, 0.0])
        
        with patch('app.services.embeddings.get_embedding_service', return_value=mock_embedder):
            result = await pipeline._is_semantically_identical("test")
        assert result is False

    @pytest.mark.asyncio
    async def test_semantic_identical_exception(self):
        from app.services.rag import RAGPipeline
        
        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline._last_query = "previous"
        pipeline._last_contexts = [{"content": "ctx"}]
        
        with patch('app.services.embeddings.get_embedding_service', side_effect=Exception("fail")):
            result = await pipeline._is_semantically_identical("test")
        assert result is False

    @pytest.mark.asyncio
    async def test_semantic_identical_high_similarity(self):
        from app.services.rag import RAGPipeline
        
        pipeline = RAGPipeline.__new__(RAGPipeline)
        pipeline._last_query = "same query"
        pipeline._last_contexts = [{"content": "ctx"}]
        pipeline._semantic_threshold = 0.85
        
        mock_embedder = MagicMock()
        mock_embedder.get_embedding = AsyncMock(return_value=[1.0, 0.0, 0.0])
        
        with patch('app.services.embeddings.get_embedding_service', return_value=mock_embedder):
            result = await pipeline._is_semantically_identical("same query")
        assert result is True


class TestGoalValidatorEdgeCases:
    @pytest.mark.asyncio
    async def test_refine_goal_llm_returns_non_json(self):
        from app.services.goal_validator import GoalValidator
        
        validator = GoalValidator()
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(
            success=True, content="not json at all"
        ))
        
        with patch('app.services.llm.get_llm_service', return_value=mock_llm):
            result = await validator.refine_goal("test goal", ["specific"])
        
        assert result["success"] is False
        assert "raw_response" in result

    @pytest.mark.asyncio
    async def test_refine_goal_llm_failure(self):
        from app.services.goal_validator import GoalValidator
        
        validator = GoalValidator()
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(
            success=False, content="", error="API error"
        ))
        
        with patch('app.services.llm.get_llm_service', return_value=mock_llm):
            result = await validator.refine_goal("test goal", ["measurable"])
        
        assert result["success"] is False


class TestUtilsLoggerEdgeCases:
    def test_get_logs_read_error(self):
        from app.utils.logger import ProcessMiningLogger
        import tempfile
        
        pm = ProcessMiningLogger(log_dir=tempfile.mkdtemp())
        pm.log_event(case_id="g1", activity="A1", resource="u1")
        
        from pathlib import Path
        pm.log_file = Path("/dev/null/nonexistent")
        
        logs = pm.get_logs_for_case("g1")
        assert logs == []

    def test_get_statistics_read_error(self):
        from app.utils.logger import ProcessMiningLogger
        import tempfile
        from pathlib import Path
        
        pm = ProcessMiningLogger(log_dir=tempfile.mkdtemp())
        pm.log_file = Path("/dev/null/nonexistent")
        
        stats = pm.get_statistics()
        assert stats["total_events"] == 0


class TestRedisCacheEdgeCases:
    @pytest.mark.asyncio
    async def test_get_or_set_redis_error_fallback(self):
        from app.core.redis_cache import RedisCache
        RedisCache._instance = None
        RedisCache._redis = None
        
        cache = RedisCache()
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("Redis down"))
        cache._redis = mock_redis
        
        getter = AsyncMock(return_value="fallback_value")
        result = await cache.get_or_set("key", getter)
        assert result == "fallback_value"
        
        RedisCache._instance = None
        RedisCache._redis = None

    @pytest.mark.asyncio
    async def test_mset_pipeline_with_ttl(self):
        from app.core.redis_cache import RedisCache
        RedisCache._instance = None
        RedisCache._redis = None
        
        cache = RedisCache()
        mock_redis = AsyncMock()
        pipe = AsyncMock()
        pipe.setex = MagicMock()
        pipe.execute = AsyncMock(return_value=[True])
        mock_redis.pipeline = MagicMock(return_value=pipe)
        cache._redis = mock_redis
        
        result = await cache.mset({"k1": "v1", "k2": "v2"}, ttl=300)
        assert result is True
        
        RedisCache._instance = None
        RedisCache._redis = None
