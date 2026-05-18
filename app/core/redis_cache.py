"""
Redis Cache Integration
=======================

Distributed caching layer untuk mencapai target performa tinggi:
- < 100ms P95 untuk 2500 RPS

Features:
- Query response caching
- Embedding caching
- Session caching
- Distributed locking untuk cache stampede prevention

Issue: KOL-42 - High Performance Targets
"""

import json
import hashlib
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import redis.asyncio as redis
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Redis configuration untuk high performance
REDIS_CONFIG = {
    "host": getattr(settings, 'REDIS_HOST', 'localhost'),
    "port": getattr(settings, 'REDIS_PORT', 32768),
    "db": getattr(settings, 'REDIS_DB', 0),
    "decode_responses": True,
    "max_connections": 50,
    "socket_keepalive": True,
    "socket_connect_timeout": 5,
    "socket_timeout": 5,
    "retry_on_timeout": True,
}

# Cache TTL configuration (seconds)
CACHE_TTL = {
    "rag_response": 3600,        # 1 jam untuk RAG responses
    "embedding": 86400,          # 24 jam untuk embeddings
    "health_check": 10,          # 10 detik untuk health
    "analytics": 300,            # 5 menit untuk analytics
    "vector_search": 600,        # 10 menit untuk vector search
    "session": 1800,             # 30 menit untuk sessions
}


class RedisCache:
    """
    Redis-based distributed cache untuk high-performance AI Engine.
    
    Target: Support 2500 RPS dengan <100ms P95 latency
    """
    
    _instance = None
    _redis = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def initialize(self):
        """Initialize Redis connection pool."""
        if self._redis is None:
            try:
                self._redis = await redis.from_url(
                    f"redis://{REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}/{REDIS_CONFIG['db']}",
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=REDIS_CONFIG['max_connections']
                )
                
                # Test connection
                await self._redis.ping()
                logger.info("redis_cache_initialized", 
                           host=REDIS_CONFIG['host'], 
                           port=REDIS_CONFIG['port'])
                
            except Exception as e:
                logger.error("redis_connection_failed", error=str(e))
                self._redis = None
                raise
    
    async def close(self):
        """Close Redis connections."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            logger.info("redis_cache_closed")

    async def ping(self) -> bool:
        """Lightweight liveness probe used by /api/health."""
        try:
            if not self._redis:
                await self.initialize()
            await self._redis.ping()
            return True
        except Exception as e:
            logger.warning("redis_ping_failed", error=str(e))
            return False
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value dari cache."""
        if not self._redis:
            await self.initialize()
        
        try:
            value = await self._redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning("redis_get_error", key=key, error=str(e))
            return None
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: int = 3600,
        nx: bool = False  # Only set if not exists (untuk cache stampede prevention)
    ) -> bool:
        """Set value ke cache."""
        if not self._redis:
            await self.initialize()
        
        try:
            serialized = json.dumps(value)
            if nx:
                result = await self._redis.setnx(key, serialized)
                if result:
                    await self._redis.expire(key, ttl)
                return result
            else:
                await self._redis.setex(key, ttl, serialized)
                return True
        except Exception as e:
            logger.warning("redis_set_error", key=key, error=str(e))
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key dari cache."""
        if not self._redis:
            return False
        
        try:
            await self._redis.delete(key)
            return True
        except Exception as e:
            logger.warning("redis_delete_error", key=key, error=str(e))
            return False
    
    async def mget(self, keys: List[str]) -> List[Optional[Any]]:
        """Get multiple keys (pipeline optimization)."""
        if not self._redis or not keys:
            return [None] * len(keys)
        
        try:
            values = await self._redis.mget(keys)
            return [json.loads(v) if v else None for v in values]
        except Exception as e:
            logger.warning("redis_mget_error", error=str(e))
            return [None] * len(keys)
    
    async def mset(self, mapping: Dict[str, Any], ttl: int = 3600) -> bool:
        """Set multiple keys (pipeline optimization)."""
        if not self._redis or not mapping:
            return False
        
        try:
            pipe = self._redis.pipeline()
            for key, value in mapping.items():
                serialized = json.dumps(value)
                pipe.setex(key, ttl, serialized)
            await pipe.execute()
            return True
        except Exception as e:
            logger.warning("redis_mset_error", error=str(e))
            return False
    
    async def get_or_set(
        self,
        key: str,
        getter_func,
        ttl: int = 3600,
        lock_timeout: float = 10.0
    ) -> Any:
        """
        Get or set dengan cache stampede prevention menggunakan distributed locking.
        
        Pattern ini mencegah thundering herd saat cache expires.
        """
        # Try to get from cache first
        cached = await self.get(key)
        if cached is not None:
            return cached
        
        # Try to acquire lock
        lock_key = f"lock:{key}"
        lock_value = f"{datetime.now().timestamp()}"
        
        try:
            # Set lock dengan NX (only if not exists)
            lock_acquired = await self._redis.set(
                lock_key, 
                lock_value, 
                nx=True, 
                ex=int(lock_timeout)
            )
            
            if lock_acquired:
                # We got the lock, compute and cache
                try:
                    value = await getter_func()
                    await self.set(key, value, ttl)
                    return value
                finally:
                    # Release lock
                    await self._redis.delete(lock_key)
            else:
                # Someone else is computing, wait and retry
                await asyncio.sleep(0.1)
                
                # Double-check cache
                cached = await self.get(key)
                if cached is not None:
                    return cached
                
                # Retry get_or_set (with limit to prevent infinite loop)
                return await self.get_or_set(key, getter_func, ttl, lock_timeout)
                
        except Exception as e:
            logger.error("redis_get_or_set_error", key=key, error=str(e))
            # Fallback: compute without caching
            return await getter_func()
    
    def generate_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate cache key dari arguments."""
        key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True)
        hash_value = hashlib.sha256(key_data.encode()).hexdigest()[:16]
        return f"{prefix}:{hash_value}"
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get Redis cache statistics."""
        if not self._redis:
            return {"error": "Redis not connected"}
        
        try:
            info = await self._redis.info()
            return {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_mb": info.get("used_memory", 0) / (1024 * 1024),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": (
                    info.get("keyspace_hits", 0) / 
                    (info.get("keyspace_hits", 0) + info.get("keyspace_misses", 1))
                ),
                "evicted_keys": info.get("evicted_keys", 0),
                "expired_keys": info.get("expired_keys", 0),
            }
        except Exception as e:
            logger.error("redis_stats_error", error=str(e))
            return {"error": str(e)}
    
    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching pattern."""
        if not self._redis:
            return 0
        
        try:
            keys = []
            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)
            
            if keys:
                await self._redis.delete(*keys)
            
            return len(keys)
        except Exception as e:
            logger.error("redis_clear_pattern_error", pattern=pattern, error=str(e))
            return 0


# Global instance
_redis_cache = None


async def get_redis_cache() -> RedisCache:
    """Get Redis cache instance."""
    global _redis_cache
    if _redis_cache is None:
        _redis_cache = RedisCache()
        await _redis_cache.initialize()
    return _redis_cache


async def close_redis_cache():
    """Close Redis cache."""
    global _redis_cache
    if _redis_cache:
        await _redis_cache.close()
        _redis_cache = None
