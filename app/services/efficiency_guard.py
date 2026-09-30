"""
Efficiency Guard Service

This module implements intelligent caching and optimization mechanisms to reduce
unnecessary API calls and improve system performance.

Key Features:
- Response caching with TTL
- Query deduplication
- Rate limiting
- Request batching
- Adaptive caching based on query patterns
"""

import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set
from collections import defaultdict, deque
import time

from app.core.logging import get_logger
from app.core.config import settings

logger = get_logger(__name__)


class CacheEntry:
    """Represents a cached response with metadata."""

    def __init__(self, response: Dict[str, Any], ttl_seconds: int = 3600):
        self.response = response
        self.created_at = datetime.now()
        self.expires_at = self.created_at + timedelta(seconds=ttl_seconds)
        self.hit_count = 0
        self.last_accessed = self.created_at

    def is_expired(self) -> bool:
        """Check if the cache entry has expired."""
        return datetime.now() > self.expires_at

    def access(self) -> Dict[str, Any]:
        """Access the cached response and update metadata."""
        self.hit_count += 1
        self.last_accessed = datetime.now()
        return self.response

    def to_dict(self) -> Dict[str, Any]:
        """Convert cache entry to dictionary for serialization."""
        return {
            "response": self.response,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "hit_count": self.hit_count,
            "last_accessed": self.last_accessed.isoformat(),
        }


class RateLimiter:
    """Rate limiter to prevent API abuse and optimize resource usage."""

    def __init__(self, max_requests: int = 100, time_window_seconds: int = 60):
        self.max_requests = max_requests
        self.time_window = timedelta(seconds=time_window_seconds)
        self.requests: Dict[str, deque] = defaultdict(deque)

    def is_allowed(self, identifier: str) -> bool:
        """
        Check if a request is allowed based on rate limits.

        Args:
            identifier: Unique identifier for the requester (user_id, group_id, etc.)

        Returns:
            True if request is allowed, False otherwise
        """
        now = datetime.now()
        request_times = self.requests[identifier]

        # Remove old requests outside the time window
        while request_times and (now - request_times[0]) > self.time_window:
            request_times.popleft()

        # Check if under limit
        if len(request_times) < self.max_requests:
            request_times.append(now)
            return True

        logger.warning(
            "rate_limit_exceeded",
            identifier=identifier,
            request_count=len(request_times),
        )
        return False

    def peek(self, identifier: str) -> bool:
        """
        Check if a request would be allowed WITHOUT consuming a quota slot.

        Performs the same time-window pruning as is_allowed so the stored
        timestamps stay consistent, but never appends a request timestamp.

        Args:
            identifier: Unique identifier for the requester (user_id, group_id, etc.)

        Returns:
            True if a request would currently be allowed, False otherwise
        """
        now = datetime.now()
        request_times = self.requests[identifier]

        # Remove old requests outside the time window
        while request_times and (now - request_times[0]) > self.time_window:
            request_times.popleft()

        return len(request_times) < self.max_requests

    def get_remaining_requests(self, identifier: str) -> int:
        """Get the number of remaining requests for an identifier."""
        now = datetime.now()
        request_times = self.requests[identifier]

        # Remove old requests
        while request_times and (now - request_times[0]) > self.time_window:
            request_times.popleft()

        return max(0, self.max_requests - len(request_times))


class QueryDeduplicator:
    """Deduplicates concurrent identical queries to avoid redundant API calls."""

    def __init__(self):
        self.pending_queries: Dict[str, asyncio.Future] = {}
        self.query_lock = asyncio.Lock()

    async def execute_or_wait(self, query_key: str, query_func: Callable) -> Any:
        """
        Execute a query or wait for an identical query to complete.

        Args:
            query_key: Unique key for the query
            query_func: Async function to execute the query

        Returns:
            Query result
        """
        async with self.query_lock:
            # Check if query is already pending
            if query_key in self.pending_queries:
                logger.debug("query_deduplication_hit", query_key=query_key)
                return await self.pending_queries[query_key]

            # Create new future for this query
            future = asyncio.Future()
            self.pending_queries[query_key] = future

        try:
            # Execute the query
            result = await query_func()
            future.set_result(result)
            return result
        except Exception as e:
            future.set_exception(e)
            raise
        finally:
            # Clean up pending query
            async with self.query_lock:
                if query_key in self.pending_queries:
                    del self.pending_queries[query_key]


class EfficiencyGuard:
    """
    Main efficiency guard service that implements caching, rate limiting,
    and query optimization to reduce unnecessary API calls.
    """

    def __init__(
        self,
        cache_ttl_seconds: int = 3600,
        max_cache_size: int = 1000,
        rate_limit_max_requests: int = 100,
        rate_limit_window_seconds: int = 60,
    ):
        self.cache: Dict[str, CacheEntry] = {}
        self.cache_ttl = cache_ttl_seconds
        self.max_cache_size = max_cache_size
        self.cache_hits = 0
        self.cache_misses = 0

        # Lock for thread-safe cache operations
        self._cache_lock = asyncio.Lock()

        self.rate_limiter = RateLimiter(
            max_requests=rate_limit_max_requests,
            time_window_seconds=rate_limit_window_seconds,
        )

        self.query_deduplicator = QueryDeduplicator()

        # Track query patterns for adaptive caching
        self.query_patterns: Dict[str, int] = defaultdict(int)
        self.high_frequency_threshold = 5

        # Statistics
        self.total_requests = 0
        self.cache_saves = 0
        self.rate_limit_blocks = 0

    def _generate_cache_key(
        self, query: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate a unique cache key for a query.

        Args:
            query: The query string
            context: Additional context (collection_name, filters, etc.)

        Returns:
            SHA256 hash of the query and context
        """
        key_data = {"query": query, "context": context or {}}
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_string.encode()).hexdigest()

    async def _cleanup_expired_cache(self):
        """Remove expired cache entries (async-safe)."""
        expired_keys = [key for key, entry in self.cache.items() if entry.is_expired()]

        for key in expired_keys:
            del self.cache[key]
            logger.debug("cache_entry_expired", key=key)

    async def _enforce_cache_size_limit(self):
        """Enforce maximum cache size by removing least recently used entries (async-safe)."""
        if len(self.cache) < self.max_cache_size:
            return

        # Sort by last accessed time (oldest first)
        sorted_entries = sorted(self.cache.items(), key=lambda x: x[1].last_accessed)

        # Remove oldest entries until under limit
        # If we are at max, we need to remove at least 1 to make room for the new one
        entries_to_remove = (len(self.cache) - self.max_cache_size) + 1
        for key, _ in sorted_entries[:entries_to_remove]:
            del self.cache[key]
            logger.debug("cache_entry_evicted", key=key)

    async def get_cached_response(
        self, query: str, context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a cached response if available and not expired (thread-safe).

        Args:
            query: The query string
            context: Additional context for the query

        Returns:
            Cached response or None if not found/expired
        """
        cache_key = self._generate_cache_key(query, context)

        async with self._cache_lock:
            # Cleanup expired entries
            await self._cleanup_expired_cache()

            if cache_key in self.cache:
                entry = self.cache[cache_key]
                if not entry.is_expired():
                    self.cache_hits += 1
                    logger.debug(
                        "cache_hit",
                        query_key=cache_key[:16],
                        hit_count=entry.hit_count + 1,
                    )
                    return entry.access()
                else:
                    # Remove expired entry
                    del self.cache[cache_key]

        self.cache_misses += 1
        logger.debug("cache_miss", query_key=cache_key[:16])
        return None

    async def cache_response(
        self,
        query: str,
        response: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """
        Cache a response for future use (thread-safe).

        Args:
            query: The query string
            response: The response to cache
            context: Additional context for the query
            ttl_seconds: Custom TTL (overrides default)
        """
        cache_key = self._generate_cache_key(query, context)
        ttl = ttl_seconds if ttl_seconds is not None else self.cache_ttl

        async with self._cache_lock:
            # Enforce cache size limit
            await self._enforce_cache_size_limit()

            # Create cache entry
            entry = CacheEntry(response, ttl_seconds=ttl)
            self.cache[cache_key] = entry
            self.cache_saves += 1

        logger.debug("cache_save", query_key=cache_key[:16], ttl_seconds=ttl)

    async def execute_with_caching(
        self,
        query: str,
        query_func: Callable,
        context: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None,
        use_deduplication: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute a query with caching and deduplication.

        Args:
            query: The query string
            query_func: Async function to execute the query
            context: Additional context for the query
            ttl_seconds: Custom TTL for caching
            use_deduplication: Whether to use query deduplication

        Returns:
            Query result
        """
        self.total_requests += 1

        # Track query pattern
        query_key = self._generate_cache_key(query, context)
        self.query_patterns[query_key] += 1

        # Try to get from cache first
        cached_response = await self.get_cached_response(query, context)
        if cached_response is not None:
            return cached_response

        # Define the query execution function
        async def execute_query():
            result = await query_func()

            # Cache the result
            await self.cache_response(
                query, result, context=context, ttl_seconds=ttl_seconds
            )

            return result

        # Execute with or without deduplication
        if use_deduplication:
            return await self.query_deduplicator.execute_or_wait(
                query_key, execute_query
            )
        else:
            return await execute_query()

    def check_rate_limit(self, identifier: str) -> bool:
        """
        Check if a request is allowed based on rate limits.

        Args:
            identifier: Unique identifier for the requester

        Returns:
            True if request is allowed, False otherwise
        """
        allowed = self.rate_limiter.is_allowed(identifier)

        if not allowed:
            self.rate_limit_blocks += 1

        return allowed

    def get_rate_limit_info(self, identifier: str) -> Dict[str, Any]:
        """
        Get rate limit information for an identifier.

        Args:
            identifier: Unique identifier for the requester

        Returns:
            Rate limit information
        """
        return {
            "identifier": identifier,
            "max_requests": self.rate_limiter.max_requests,
            "time_window_seconds": self.rate_limiter.time_window.total_seconds(),
            "remaining_requests": self.rate_limiter.get_remaining_requests(identifier),
            "is_allowed": self.rate_limiter.peek(identifier),
        }

    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate_percent": round(hit_rate, 2),
            "cache_size": len(self.cache),
            "max_cache_size": self.max_cache_size,
            "cache_saves": self.cache_saves,
            "total_requests": self.total_requests,
        }

    def get_high_frequency_queries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the most frequently executed queries.

        Args:
            limit: Maximum number of queries to return

        Returns:
            List of high-frequency queries with their counts
        """
        sorted_queries = sorted(
            self.query_patterns.items(), key=lambda x: x[1], reverse=True
        )

        return [
            {"query_key": key[:32], "frequency": count}
            for key, count in sorted_queries[:limit]
            if count >= self.high_frequency_threshold
        ]

    async def clear_cache(self) -> None:
        """Clear all cached responses (thread-safe)."""
        async with self._cache_lock:
            cache_size = len(self.cache)
            self.cache.clear()
        logger.info("cache_cleared", entries_removed=cache_size)

    async def clear_expired_cache(self) -> int:
        """
        Clear expired cache entries (thread-safe).

        Returns:
            Number of entries removed
        """
        async with self._cache_lock:
            initial_size = len(self.cache)
            await self._cleanup_expired_cache()
            removed = initial_size - len(self.cache)
        logger.info("expired_cache_cleared", entries_removed=removed)
        return removed

    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive efficiency guard statistics."""
        return {
            "cache": self.get_cache_statistics(),
            "rate_limit": {
                "total_requests": self.total_requests,
                "rate_limit_blocks": self.rate_limit_blocks,
                "max_requests_per_window": self.rate_limiter.max_requests,
                "time_window_seconds": self.rate_limiter.time_window.total_seconds(),
            },
            "query_patterns": {
                "unique_queries": len(self.query_patterns),
                "high_frequency_queries": self.get_high_frequency_queries(),
            },
            "performance": {
                "cache_hit_rate_percent": round(
                    (self.cache_hits / (self.cache_hits + self.cache_misses) * 100)
                    if (self.cache_hits + self.cache_misses) > 0
                    else 0,
                    2,
                ),
                "requests_saved_by_cache": self.cache_hits,
                "requests_blocked_by_rate_limit": self.rate_limit_blocks,
            },
        }


# Singleton instance
_efficiency_guard: Optional[EfficiencyGuard] = None


def get_efficiency_guard() -> EfficiencyGuard:
    """Get the singleton EfficiencyGuard instance."""
    global _efficiency_guard
    if _efficiency_guard is None:
        _efficiency_guard = EfficiencyGuard(
            cache_ttl_seconds=getattr(settings, "CACHE_TTL_SECONDS", 3600),
            max_cache_size=getattr(settings, "MAX_CACHE_SIZE", 1000),
            rate_limit_max_requests=getattr(settings, "RATE_LIMIT_MAX_REQUESTS", 100),
            rate_limit_window_seconds=getattr(
                settings, "RATE_LIMIT_WINDOW_SECONDS", 60
            ),
        )
    return _efficiency_guard
