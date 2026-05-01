"""
Tests for app/core/redis_cache.py
"""
import pytest
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
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
    client.info = AsyncMock(return_value={
        "connected_clients": 5,
        "used_memory": 1048576,
        "keyspace_hits": 100,
        "keyspace_misses": 20,
        "evicted_keys": 0,
        "expired_keys": 10,
    })
    
    # Pipeline mock
    pipe = AsyncMock()
    pipe.setex = MagicMock()
    pipe.execute = AsyncMock(return_value=[True, True])
    client.pipeline = MagicMock(return_value=pipe)
    
    # scan_iter mock
    async def fake_scan_iter(match=None):
        for key in ["key1", "key2", "key3"]:
            yield key
    client.scan_iter = fake_scan_iter
    
    return client


@pytest.fixture
def redis_cache(mock_redis_client):
    """Create a RedisCache instance with mocked Redis."""
    from app.core.redis_cache import RedisCache
    
    # Reset singleton
    RedisCache._instance = None
    RedisCache._redis = None
    
    cache = RedisCache()
    cache._redis = mock_redis_client
    return cache


class TestRedisCacheInit:
    """Test RedisCache initialization."""
    
    @pytest.mark.asyncio
    async def test_singleton_pattern(self):
        """RedisCache should be a singleton."""
        from app.core.redis_cache import RedisCache
        RedisCache._instance = None
        RedisCache._redis = None
        
        cache1 = RedisCache()
        cache2 = RedisCache()
        assert cache1 is cache2
        
        # Cleanup
        RedisCache._instance = None
        RedisCache._redis = None
    
    @pytest.mark.asyncio
    async def test_initialize_success(self, mock_redis_client):
        """Initialize should connect to Redis."""
        from app.core.redis_cache import RedisCache
        RedisCache._instance = None
        RedisCache._redis = None
        
        cache = RedisCache()
        
        with patch("app.core.redis_cache.redis.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_from_url.return_value = mock_redis_client
            await cache.initialize()
            
            assert cache._redis is mock_redis_client
            mock_redis_client.ping.assert_called_once()
        
        RedisCache._instance = None
        RedisCache._redis = None
    
    @pytest.mark.asyncio
    async def test_initialize_failure(self):
        """Initialize should handle connection failure."""
        from app.core.redis_cache import RedisCache
        RedisCache._instance = None
        RedisCache._redis = None
        
        cache = RedisCache()
        
        with patch("app.core.redis_cache.redis.from_url", new_callable=AsyncMock) as mock_from_url:
            mock_from_url.side_effect = ConnectionError("Cannot connect")
            
            with pytest.raises(ConnectionError):
                await cache.initialize()
            
            assert cache._redis is None
        
        RedisCache._instance = None
        RedisCache._redis = None
    
    @pytest.mark.asyncio
    async def test_close(self, redis_cache, mock_redis_client):
        """Close should disconnect Redis."""
        await redis_cache.close()
        mock_redis_client.close.assert_called_once()
        assert redis_cache._redis is None


class TestRedisCacheGet:
    """Test RedisCache.get method."""
    
    @pytest.mark.asyncio
    async def test_get_existing_key(self, redis_cache, mock_redis_client):
        """Get should return deserialized value for existing key."""
        mock_redis_client.get.return_value = json.dumps({"answer": "hello"})
        
        result = await redis_cache.get("test_key")
        assert result == {"answer": "hello"}
        mock_redis_client.get.assert_called_with("test_key")
    
    @pytest.mark.asyncio
    async def test_get_missing_key(self, redis_cache, mock_redis_client):
        """Get should return None for missing key."""
        mock_redis_client.get.return_value = None
        
        result = await redis_cache.get("missing_key")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_error_returns_none(self, redis_cache, mock_redis_client):
        """Get should return None on Redis error."""
        mock_redis_client.get.side_effect = Exception("Redis error")
        
        result = await redis_cache.get("error_key")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_auto_initializes(self, mock_redis_client):
        """Get should auto-initialize if not connected."""
        from app.core.redis_cache import RedisCache
        RedisCache._instance = None
        RedisCache._redis = None
        
        cache = RedisCache()
        cache._redis = None
        
        with patch.object(cache, "initialize", new_callable=AsyncMock) as mock_init:
            async def set_redis():
                cache._redis = mock_redis_client
            mock_init.side_effect = set_redis
            mock_redis_client.get.return_value = json.dumps("value")
            
            result = await cache.get("key")
            mock_init.assert_called_once()
        
        RedisCache._instance = None
        RedisCache._redis = None


class TestRedisCacheSet:
    """Test RedisCache.set method."""
    
    @pytest.mark.asyncio
    async def test_set_basic(self, redis_cache, mock_redis_client):
        """Set should serialize and store value."""
        result = await redis_cache.set("key", {"data": 123}, ttl=600)
        assert result is True
        mock_redis_client.setex.assert_called_with("key", 600, json.dumps({"data": 123}))
    
    @pytest.mark.asyncio
    async def test_set_nx_success(self, redis_cache, mock_redis_client):
        """Set with nx=True should use setnx."""
        mock_redis_client.setnx.return_value = True
        
        result = await redis_cache.set("key", "value", ttl=300, nx=True)
        assert result is True
        mock_redis_client.setnx.assert_called_once()
        mock_redis_client.expire.assert_called_with("key", 300)
    
    @pytest.mark.asyncio
    async def test_set_nx_already_exists(self, redis_cache, mock_redis_client):
        """Set with nx=True should return False if key exists."""
        mock_redis_client.setnx.return_value = False
        
        result = await redis_cache.set("key", "value", nx=True)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_set_error_returns_false(self, redis_cache, mock_redis_client):
        """Set should return False on error."""
        mock_redis_client.setex.side_effect = Exception("Write error")
        
        result = await redis_cache.set("key", "value")
        assert result is False


class TestRedisCacheDelete:
    """Test RedisCache.delete method."""
    
    @pytest.mark.asyncio
    async def test_delete_success(self, redis_cache, mock_redis_client):
        """Delete should remove key."""
        result = await redis_cache.delete("key")
        assert result is True
        mock_redis_client.delete.assert_called_with("key")
    
    @pytest.mark.asyncio
    async def test_delete_not_connected(self):
        """Delete should return False if not connected."""
        from app.core.redis_cache import RedisCache
        RedisCache._instance = None
        RedisCache._redis = None
        
        cache = RedisCache()
        cache._redis = None
        result = await cache.delete("key")
        assert result is False
        
        RedisCache._instance = None
        RedisCache._redis = None
    
    @pytest.mark.asyncio
    async def test_delete_error(self, redis_cache, mock_redis_client):
        """Delete should return False on error."""
        mock_redis_client.delete.side_effect = Exception("Delete error")
        
        result = await redis_cache.delete("key")
        assert result is False


class TestRedisCacheMget:
    """Test RedisCache.mget method."""
    
    @pytest.mark.asyncio
    async def test_mget_success(self, redis_cache, mock_redis_client):
        """Mget should return deserialized values."""
        mock_redis_client.mget.return_value = [
            json.dumps("val1"),
            None,
            json.dumps({"key": "val3"})
        ]
        
        result = await redis_cache.mget(["k1", "k2", "k3"])
        assert result == ["val1", None, {"key": "val3"}]
    
    @pytest.mark.asyncio
    async def test_mget_empty_keys(self, redis_cache):
        """Mget with empty keys should return empty list."""
        result = await redis_cache.mget([])
        assert result == []
    
    @pytest.mark.asyncio
    async def test_mget_not_connected(self):
        """Mget should return Nones if not connected."""
        from app.core.redis_cache import RedisCache
        RedisCache._instance = None
        RedisCache._redis = None
        
        cache = RedisCache()
        cache._redis = None
        result = await cache.mget(["k1", "k2"])
        assert result == [None, None]
        
        RedisCache._instance = None
        RedisCache._redis = None
    
    @pytest.mark.asyncio
    async def test_mget_error(self, redis_cache, mock_redis_client):
        """Mget should return Nones on error."""
        mock_redis_client.mget.side_effect = Exception("Error")
        
        result = await redis_cache.mget(["k1", "k2"])
        assert result == [None, None]


class TestRedisCacheMset:
    """Test RedisCache.mset method."""
    
    @pytest.mark.asyncio
    async def test_mset_success(self, redis_cache, mock_redis_client):
        """Mset should pipeline multiple setex calls."""
        mapping = {"k1": "v1", "k2": {"nested": True}}
        result = await redis_cache.mset(mapping, ttl=600)
        assert result is True
        
        pipe = mock_redis_client.pipeline()
        pipe.execute.assert_called()
    
    @pytest.mark.asyncio
    async def test_mset_empty_mapping(self, redis_cache):
        """Mset with empty mapping should return False."""
        result = await redis_cache.mset({})
        assert result is False
    
    @pytest.mark.asyncio
    async def test_mset_not_connected(self):
        """Mset should return False if not connected."""
        from app.core.redis_cache import RedisCache
        RedisCache._instance = None
        RedisCache._redis = None
        
        cache = RedisCache()
        cache._redis = None
        result = await cache.mset({"k": "v"})
        assert result is False
        
        RedisCache._instance = None
        RedisCache._redis = None
    
    @pytest.mark.asyncio
    async def test_mset_error(self, redis_cache, mock_redis_client):
        """Mset should return False on error."""
        pipe = mock_redis_client.pipeline()
        pipe.execute.side_effect = Exception("Pipeline error")
        
        result = await redis_cache.mset({"k": "v"})
        assert result is False


class TestRedisCacheGetOrSet:
    """Test RedisCache.get_or_set method."""
    
    @pytest.mark.asyncio
    async def test_get_or_set_cache_hit(self, redis_cache, mock_redis_client):
        """get_or_set should return cached value on hit."""
        mock_redis_client.get.return_value = json.dumps("cached_value")
        
        getter = AsyncMock(return_value="computed")
        result = await redis_cache.get_or_set("key", getter, ttl=600)
        
        assert result == "cached_value"
        getter.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_get_or_set_cache_miss_computes(self, redis_cache, mock_redis_client):
        """get_or_set should compute and cache on miss."""
        # First get returns None (miss), lock acquired
        mock_redis_client.get.return_value = None
        mock_redis_client.set.return_value = True
        
        getter = AsyncMock(return_value="computed_value")
        result = await redis_cache.get_or_set("key", getter, ttl=600)
        
        assert result == "computed_value"
        getter.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_or_set_error_fallback(self, redis_cache, mock_redis_client):
        """get_or_set should fallback to getter on Redis error."""
        mock_redis_client.get.side_effect = Exception("Redis down")
        
        getter = AsyncMock(return_value="fallback_value")
        result = await redis_cache.get_or_set("key", getter)
        
        assert result == "fallback_value"


class TestRedisCacheGenerateKey:
    """Test RedisCache.generate_key method."""
    
    def test_generate_key_deterministic(self, redis_cache):
        """Same inputs should produce same key."""
        key1 = redis_cache.generate_key("prefix", "arg1", "arg2", opt="val")
        key2 = redis_cache.generate_key("prefix", "arg1", "arg2", opt="val")
        assert key1 == key2
    
    def test_generate_key_different_inputs(self, redis_cache):
        """Different inputs should produce different keys."""
        key1 = redis_cache.generate_key("prefix", "arg1")
        key2 = redis_cache.generate_key("prefix", "arg2")
        assert key1 != key2
    
    def test_generate_key_format(self, redis_cache):
        """Key should have prefix:hash format."""
        key = redis_cache.generate_key("rag", "query")
        assert key.startswith("rag:")
        assert len(key) == len("rag:") + 16  # 16 char hash


class TestRedisCacheStats:
    """Test RedisCache.get_cache_stats method."""
    
    @pytest.mark.asyncio
    async def test_get_cache_stats(self, redis_cache, mock_redis_client):
        """get_cache_stats should return formatted stats."""
        result = await redis_cache.get_cache_stats()
        
        assert result["connected_clients"] == 5
        assert result["used_memory_mb"] == 1.0
        assert result["keyspace_hits"] == 100
        assert result["keyspace_misses"] == 20
        assert result["hit_rate"] == 100 / 120
        assert result["evicted_keys"] == 0
        assert result["expired_keys"] == 10
    
    @pytest.mark.asyncio
    async def test_get_cache_stats_not_connected(self):
        """get_cache_stats should return error if not connected."""
        from app.core.redis_cache import RedisCache
        RedisCache._instance = None
        RedisCache._redis = None
        
        cache = RedisCache()
        cache._redis = None
        result = await cache.get_cache_stats()
        assert "error" in result
        
        RedisCache._instance = None
        RedisCache._redis = None
    
    @pytest.mark.asyncio
    async def test_get_cache_stats_error(self, redis_cache, mock_redis_client):
        """get_cache_stats should handle errors."""
        mock_redis_client.info.side_effect = Exception("Info error")
        
        result = await redis_cache.get_cache_stats()
        assert "error" in result


class TestRedisCacheClearPattern:
    """Test RedisCache.clear_pattern method."""
    
    @pytest.mark.asyncio
    async def test_clear_pattern_success(self, redis_cache, mock_redis_client):
        """clear_pattern should delete matching keys."""
        result = await redis_cache.clear_pattern("prefix:*")
        assert result == 3  # 3 keys from fake_scan_iter
    
    @pytest.mark.asyncio
    async def test_clear_pattern_not_connected(self):
        """clear_pattern should return 0 if not connected."""
        from app.core.redis_cache import RedisCache
        RedisCache._instance = None
        RedisCache._redis = None
        
        cache = RedisCache()
        cache._redis = None
        result = await cache.clear_pattern("*")
        assert result == 0
        
        RedisCache._instance = None
        RedisCache._redis = None
    
    @pytest.mark.asyncio
    async def test_clear_pattern_error(self, redis_cache, mock_redis_client):
        """clear_pattern should return 0 on error."""
        async def error_scan(match=None):
            raise Exception("Scan error")
            yield  # Make it a generator
        
        redis_cache._redis.scan_iter = error_scan
        result = await redis_cache.clear_pattern("*")
        assert result == 0


class TestRedisCacheModule:
    """Test module-level functions."""
    
    @pytest.mark.asyncio
    async def test_get_redis_cache_singleton(self):
        """get_redis_cache should return singleton."""
        import app.core.redis_cache as module
        module._redis_cache = None
        
        with patch("app.core.redis_cache.RedisCache") as MockCache:
            instance = AsyncMock()
            instance.initialize = AsyncMock()
            MockCache.return_value = instance
            MockCache._instance = None
            MockCache._redis = None
            
            result = await module.get_redis_cache()
            instance.initialize.assert_called_once()
        
        module._redis_cache = None
    
    @pytest.mark.asyncio
    async def test_close_redis_cache(self):
        """close_redis_cache should close and clear singleton."""
        import app.core.redis_cache as module
        
        mock_cache = AsyncMock()
        module._redis_cache = mock_cache
        
        await module.close_redis_cache()
        mock_cache.close.assert_called_once()
        assert module._redis_cache is None
    
    @pytest.mark.asyncio
    async def test_close_redis_cache_when_none(self):
        """close_redis_cache should be safe when no cache exists."""
        import app.core.redis_cache as module
        module._redis_cache = None
        
        await module.close_redis_cache()  # Should not raise
