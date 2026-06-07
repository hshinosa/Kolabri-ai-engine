"""
Cache Analyzer & Pre-warm
=========================

Priority 2: Cache Hit Rate Optimization

Features:
- Track query frequency
- Auto-identify hot queries
- Pre-warm cache untuk high-frequency queries
- Cache hit rate monitoring
"""

import asyncio
from typing import Dict, Any, List
from collections import defaultdict
from datetime import datetime, timedelta

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis_cache import get_redis_cache, CACHE_TTL
from app.services.llm import OpenAILLMService as OptimizedLLMService

logger = get_logger(__name__)


class CacheAnalyzer:
    """Analyze dan optimize cache performance."""
    
    def __init__(self):
        self.query_stats = defaultdict(lambda: {
            "count": 0,
            "first_seen": datetime.now(),
            "last_seen": datetime.now(),
        })
        self.cache_hits = 0
        self.cache_misses = 0
        self._initialized = False
    
    async def initialize(self):
        """Initialize analyzer."""
        if not self._initialized:
            await get_redis_cache()
            self._initialized = True
    
    def track_query(self, query: str, hit: bool):
        """Track query frequency dan cache performance."""
        now = datetime.now()
        stats = self.query_stats[query]
        stats["count"] += 1
        stats["last_seen"] = now
        
        if hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1
    
    def get_hot_queries(self, top_n: int = 20) -> List[Dict[str, Any]]:
        """Get top N most frequent queries."""
        sorted_queries = sorted(
            self.query_stats.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )
        
        return [
            {
                "query": query,
                "count": stats["count"],
                "first_seen": stats["first_seen"].isoformat(),
                "last_seen": stats["last_seen"].isoformat(),
            }
            for query, stats in sorted_queries[:top_n]
        ]
    
    def get_cache_hit_rate(self) -> float:
        """Get current cache hit rate."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return (self.cache_hits / total) * 100
    
    async def prewarm_cache(
        self,
        queries: List[str],
        llm_service: OptimizedLLMService,
        collection_name: str = "default"
    ) -> Dict[str, Any]:
        """
        Pre-warm cache untuk high-frequency queries.
        
        Args:
            queries: List of queries untuk pre-compute
            llm_service: LLM service untuk generate responses
            collection_name: Collection name
        
        Returns:
            Stats pre-warming
        """
        await self.initialize()
        
        logger.info("cache_prewarm_started", queries=len(queries))
        
        warmed = 0
        failed = 0
        total_time = 0
        
        for i, query in enumerate(queries, 1):
            try:
                # Generate response
                start = datetime.now()
                result = await llm_service.generate(
                    prompt=query,
                    system_prompt="Anda adalah asisten AI."
                )
                elapsed = (datetime.now() - start).total_seconds() * 1000
                total_time += elapsed
                
                if result.success:
                    # Cache result
                    redis_cache = await get_redis_cache()
                    cache_key = f"prewarm:{collection_name}:{hash(query)}"
                    await redis_cache.set(
                        cache_key,
                        {"answer": result.content, "tokens": result.tokens_used},
                        ttl=CACHE_TTL["rag_response"]
                    )
                    warmed += 1
                    logger.debug("cache_prewarmed", query=query[:30], time_ms=elapsed)
                else:
                    failed += 1
                    
            except Exception:
                failed += 1
                logger.exception("cache_prewarm_failed", query=query[:30])
            
            # Progress log setiap 10 queries
            if i % 10 == 0:
                logger.info("cache_prewarm_progress", current=i, total=len(queries))
        
        avg_time = total_time / warmed if warmed > 0 else 0
        
        result = {
            "total": len(queries),
            "warmed": warmed,
            "failed": failed,
            "avg_time_ms": avg_time,
            "total_time_ms": total_time,
        }
        
        logger.info("cache_prewarm_completed", **result)
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache analyzer statistics."""
        return {
            "total_queries": len(self.query_stats),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate": self.get_cache_hit_rate(),
            "hot_queries": self.get_hot_queries(10),
        }


# Global instance
_cache_analyzer = None


async def get_cache_analyzer() -> CacheAnalyzer:
    """Get singleton instance."""
    global _cache_analyzer
    if _cache_analyzer is None:
        _cache_analyzer = CacheAnalyzer()
        await _cache_analyzer.initialize()
    return _cache_analyzer
