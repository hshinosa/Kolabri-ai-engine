"""Tests for app/core/cache_analyzer.py"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


@pytest.fixture
def cache_analyzer():
    """Fresh CacheAnalyzer instance."""
    from app.core.cache_analyzer import CacheAnalyzer
    return CacheAnalyzer()


class TestCacheAnalyzerTrackQuery:
    def test_track_query_hit(self, cache_analyzer):
        cache_analyzer.track_query("what is AI?", hit=True)
        
        assert cache_analyzer.cache_hits == 1
        assert cache_analyzer.cache_misses == 0
        assert cache_analyzer.query_stats["what is AI?"]["count"] == 1
    
    def test_track_query_miss(self, cache_analyzer):
        cache_analyzer.track_query("what is ML?", hit=False)
        
        assert cache_analyzer.cache_hits == 0
        assert cache_analyzer.cache_misses == 1
    
    def test_track_multiple_queries(self, cache_analyzer):
        cache_analyzer.track_query("q1", hit=True)
        cache_analyzer.track_query("q1", hit=True)
        cache_analyzer.track_query("q2", hit=False)
        cache_analyzer.track_query("q1", hit=True)
        
        assert cache_analyzer.query_stats["q1"]["count"] == 3
        assert cache_analyzer.query_stats["q2"]["count"] == 1
        assert cache_analyzer.cache_hits == 3
        assert cache_analyzer.cache_misses == 1


class TestCacheAnalyzerGetHotQueries:
    def test_get_hot_queries_empty(self, cache_analyzer):
        result = cache_analyzer.get_hot_queries()
        assert result == []
    
    def test_get_hot_queries_sorted_by_count(self, cache_analyzer):
        for _ in range(5):
            cache_analyzer.track_query("popular", hit=True)
        for _ in range(2):
            cache_analyzer.track_query("medium", hit=True)
        cache_analyzer.track_query("rare", hit=False)
        
        result = cache_analyzer.get_hot_queries(top_n=3)
        assert len(result) == 3
        assert result[0]["query"] == "popular"
        assert result[0]["count"] == 5
        assert result[1]["query"] == "medium"
        assert result[1]["count"] == 2
        assert result[2]["query"] == "rare"
        assert result[2]["count"] == 1
    
    def test_get_hot_queries_respects_top_n(self, cache_analyzer):
        for i in range(10):
            cache_analyzer.track_query(f"query_{i}", hit=True)
        
        result = cache_analyzer.get_hot_queries(top_n=3)
        assert len(result) == 3
    
    def test_get_hot_queries_includes_timestamps(self, cache_analyzer):
        cache_analyzer.track_query("q1", hit=True)
        
        result = cache_analyzer.get_hot_queries()
        assert "first_seen" in result[0]
        assert "last_seen" in result[0]


class TestCacheAnalyzerHitRate:
    def test_hit_rate_zero_when_empty(self, cache_analyzer):
        assert cache_analyzer.get_cache_hit_rate() == 0.0
    
    def test_hit_rate_100_percent(self, cache_analyzer):
        cache_analyzer.cache_hits = 10
        cache_analyzer.cache_misses = 0
        assert cache_analyzer.get_cache_hit_rate() == 100.0
    
    def test_hit_rate_50_percent(self, cache_analyzer):
        cache_analyzer.cache_hits = 5
        cache_analyzer.cache_misses = 5
        assert cache_analyzer.get_cache_hit_rate() == 50.0
    
    def test_hit_rate_calculation(self, cache_analyzer):
        cache_analyzer.cache_hits = 80
        cache_analyzer.cache_misses = 20
        assert cache_analyzer.get_cache_hit_rate() == 80.0


class TestCacheAnalyzerPrewarm:
    @pytest.mark.asyncio
    async def test_prewarm_success(self, cache_analyzer):
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(
            success=True, content="answer", tokens_used=50
        ))
        
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        
        with patch("app.core.cache_analyzer.get_redis_cache", new_callable=AsyncMock) as mock_get_redis:
            mock_get_redis.return_value = mock_redis
            cache_analyzer._initialized = True
            
            result = await cache_analyzer.prewarm_cache(
                queries=["q1", "q2"],
                llm_service=mock_llm,
                collection_name="test"
            )
        
        assert result["total"] == 2
        assert result["warmed"] == 2
        assert result["failed"] == 0
        assert mock_llm.generate.call_count == 2
    
    @pytest.mark.asyncio
    async def test_prewarm_partial_failure(self, cache_analyzer):
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(
            success=False, content="", tokens_used=0, error="LLM error"
        ))
        
        mock_redis = AsyncMock()
        
        with patch("app.core.cache_analyzer.get_redis_cache", new_callable=AsyncMock) as mock_get_redis:
            mock_get_redis.return_value = mock_redis
            cache_analyzer._initialized = True
            
            result = await cache_analyzer.prewarm_cache(
                queries=["q1"],
                llm_service=mock_llm
            )
        
        assert result["warmed"] == 0
        assert result["failed"] == 1
    
    @pytest.mark.asyncio
    async def test_prewarm_exception_handling(self, cache_analyzer):
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(side_effect=Exception("Network error"))
        
        mock_redis = AsyncMock()
        
        with patch("app.core.cache_analyzer.get_redis_cache", new_callable=AsyncMock) as mock_get_redis:
            mock_get_redis.return_value = mock_redis
            cache_analyzer._initialized = True
            
            result = await cache_analyzer.prewarm_cache(
                queries=["q1"],
                llm_service=mock_llm
            )
        
        assert result["warmed"] == 0
        assert result["failed"] == 1


class TestCacheAnalyzerStats:
    def test_get_stats(self, cache_analyzer):
        cache_analyzer.track_query("q1", hit=True)
        cache_analyzer.track_query("q2", hit=False)
        
        stats = cache_analyzer.get_stats()
        assert stats["total_queries"] == 2
        assert stats["cache_hits"] == 1
        assert stats["cache_misses"] == 1
        assert stats["hit_rate"] == 50.0
        assert len(stats["hot_queries"]) == 2


class TestCacheAnalyzerModule:
    @pytest.mark.asyncio
    async def test_get_cache_analyzer_singleton(self):
        import app.core.cache_analyzer as module
        module._cache_analyzer = None
        
        with patch("app.core.cache_analyzer.get_redis_cache", new_callable=AsyncMock):
            analyzer = await module.get_cache_analyzer()
            assert analyzer is not None
            assert analyzer._initialized is True
        
        module._cache_analyzer = None
