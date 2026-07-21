"""
Batch Processing Endpoint
=========================

High-throughput batch endpoint untuk mencapai target:
- 2500 RPS dengan <100ms P95 latency

Fitur:
- Parallel processing dengan asyncio.gather
- Connection pooling
- Response caching
- Error isolation (satu failure tidak mengganggu batch lain)

Issue: KOL-42 - High Performance Targets
"""

import asyncio
import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis_cache import get_redis_cache, CACHE_TTL
from app.services.llm import get_llm_service
from app.services.rag import get_rag_pipeline

logger = get_logger(__name__)

router = APIRouter()

# Configuration untuk batch processing
BATCH_CONFIG = {
    "max_batch_size": 50,  # Maksimum items per batch
    "max_concurrent": 20,  # Maksimum concurrent processing
    "timeout_seconds": 30,  # Timeout per item
    "enable_caching": True,  # Enable response caching
    "cache_ttl": 3600,  # Cache TTL in seconds
}


class BatchAskRequest(BaseModel):
    """Single request dalam batch."""

    query: str = Field(..., min_length=1, max_length=2000)
    course_id: str
    user_name: Optional[str] = None
    chat_space_id: Optional[str] = None
    request_id: Optional[str] = None  # Untuk tracking


class BatchAskResponse(BaseModel):
    """Response untuk batch processing."""

    request_id: Optional[str]
    success: bool
    answer: str
    error: Optional[str] = None
    processing_time_ms: float = 0.0
    from_cache: bool = False


class BatchAskRequestList(BaseModel):
    """List of batch requests."""

    requests: List[BatchAskRequest] = Field(
        ..., max_length=BATCH_CONFIG["max_batch_size"]
    )
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")


class BatchAskResponseList(BaseModel):
    """List of batch responses."""

    results: List[BatchAskResponse]
    total_requests: int
    successful_count: int
    failed_count: int
    total_processing_time_ms: float
    from_cache_count: int


@router.post(
    "/ask/batch",
    response_model=BatchAskResponseList,
    tags=["Batch Processing"],
    summary="Process multiple RAG queries in batch (high throughput)",
)
async def ask_batch(request_list: BatchAskRequestList):
    """
    Process multiple RAG queries in parallel untuk high throughput.

    Target: Support 2500 RPS dengan <100ms P95 latency per request.

    - Parallel processing dengan asyncio.gather
    - Response caching untuk repeated queries
    - Error isolation: satu failure tidak mengganggu batch lain
    - Connection pooling untuk optimal resource usage

    Example:
        POST /ask/batch
        {
            "requests": [
                {"query": "Apa itu ML?", "course_id": "c1"},
                {"query": "Jelaskan AI", "course_id": "c1"}
            ],
            "priority": "high"
        }
    """
    start_time = time.time()

    if len(request_list.requests) > BATCH_CONFIG["max_batch_size"]:
        raise HTTPException(
            status_code=400,
            detail=f"Batch size exceeds maximum of {BATCH_CONFIG['max_batch_size']}",
        )

    # Semaphore untuk limit concurrency
    semaphore = asyncio.Semaphore(BATCH_CONFIG["max_concurrent"])

    # Process all requests in parallel dengan semaphore
    tasks = [
        _process_single_with_semaphore(semaphore, req) for req in request_list.requests
    ]

    # Execute dengan timeout
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Format responses
    responses = []
    successful = 0
    failed = 0
    from_cache = 0

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            # Handle error
            responses.append(
                BatchAskResponse(
                    request_id=request_list.requests[i].request_id,
                    success=False,
                    answer="",
                    error=str(result),
                    processing_time_ms=0.0,
                    from_cache=False,
                )
            )
            failed += 1
        else:
            responses.append(result)
            if result.success:
                successful += 1
            else:
                failed += 1
            if result.from_cache:
                from_cache += 1

    total_time = (time.time() - start_time) * 1000

    logger.info(
        "batch_processing_completed",
        total_requests=len(request_list.requests),
        successful=successful,
        failed=failed,
        from_cache=from_cache,
        total_time_ms=round(total_time, 2),
        avg_time_per_req=round(total_time / len(request_list.requests), 2)
        if request_list.requests
        else 0,
    )

    return BatchAskResponseList(
        results=responses,
        total_requests=len(request_list.requests),
        successful_count=successful,
        failed_count=failed,
        total_processing_time_ms=round(total_time, 2),
        from_cache_count=from_cache,
    )


async def _process_single_with_semaphore(
    semaphore: asyncio.Semaphore, request: BatchAskRequest
) -> BatchAskResponse:
    """Process single request dengan semaphore untuk limit concurrency."""
    async with semaphore:
        return await _process_single_ask(request)


async def _process_single_ask(request: BatchAskRequest) -> BatchAskResponse:
    """
    Process single RAG query dengan caching.

    Target: <50ms untuk cache hit, <100ms untuk cache miss
    """
    start_time = time.time()

    try:
        # Generate cache key
        cache_key = None
        if BATCH_CONFIG["enable_caching"]:
            cache_key = _generate_cache_key(request)

            # Try to get from cache
            redis_cache = await get_redis_cache()
            cached = await redis_cache.get(cache_key)

            if cached:
                processing_time = (time.time() - start_time) * 1000
                logger.debug(
                    "batch_cache_hit",
                    request_id=request.request_id,
                    processing_time_ms=round(processing_time, 2),
                )
                return BatchAskResponse(
                    request_id=request.request_id,
                    success=True,
                    answer=cached.get("answer", ""),
                    processing_time_ms=round(processing_time, 2),
                    from_cache=True,
                )

        # Process dengan RAG pipeline
        rag_pipeline = get_rag_pipeline()

        result = await rag_pipeline.query(
            query=request.query,
            collection_name=f"course_{request.course_id}",
            n_results=settings.TOP_K_RESULTS,
            use_cache=False,  # Kita handle caching di sini
        )

        processing_time = (time.time() - start_time) * 1000

        # Format answer
        answer = result.answer
        if result.sources:
            sources_text = "\n\n📚 *Sumber:*\n"
            for i, src in enumerate(result.sources[:3], 1):
                source_name = src.get("source", "Dokumen")
                page = src.get("page")
                if page:
                    sources_text += f"{i}. {source_name} (hal. {page})\n"
                else:
                    sources_text += f"{i}. {source_name}\n"
            answer += sources_text

        # Cache successful result
        if BATCH_CONFIG["enable_caching"] and result.success and cache_key:
            redis_cache = await get_redis_cache()
            await redis_cache.set(
                cache_key,
                {"answer": answer, "sources": result.sources},
                ttl=BATCH_CONFIG["cache_ttl"],
            )

        return BatchAskResponse(
            request_id=request.request_id,
            success=result.success,
            answer=answer,
            error=result.error,
            processing_time_ms=round(processing_time, 2),
            from_cache=False,
        )

    except asyncio.TimeoutError:
        processing_time = (time.time() - start_time) * 1000
        logger.error(
            "batch_request_timeout",
            request_id=request.request_id,
            query=request.query[:50],
        )
        return BatchAskResponse(
            request_id=request.request_id,
            success=False,
            answer="",
            error="Request timeout",
            processing_time_ms=round(processing_time, 2),
            from_cache=False,
        )

    except Exception:
        processing_time = (time.time() - start_time) * 1000
        logger.exception(
            "batch_request_failed",
            request_id=request.request_id,
        )
        return BatchAskResponse(
            request_id=request.request_id,
            success=False,
            answer="",
            error="Internal error",
            processing_time_ms=round(processing_time, 2),
            from_cache=False,
        )


def _generate_cache_key(request: BatchAskRequest) -> str:
    """Generate cache key untuk request."""
    import hashlib

    key_data = f"{request.query}:{request.course_id}"
    hash_value = hashlib.sha256(key_data.encode()).hexdigest()[:16]
    return f"rag:batch:{hash_value}"


@router.post(
    "/ask/batch/precomputed",
    response_model=BatchAskResponseList,
    tags=["Batch Processing"],
    summary="Process batch dengan pre-computed responses (fastest)",
)
async def ask_batch_precomputed(request_list: BatchAskRequestList):
    """
    Batch endpoint yang hanya mengembalikan pre-computed responses.

    Jika query tidak ada di cache, return error.
    Ini untuk skenario dimana kita hanya menerima query yang sudah dipre-compute.

    Target: <10ms P95 latency
    """
    start_time = time.time()

    redis_cache = await get_redis_cache()

    # Generate cache keys
    cache_keys = [_generate_cache_key(req) for req in request_list.requests]

    # Get all dari cache dalam satu call (pipeline optimization)
    cached_values = await redis_cache.mget(cache_keys)

    responses = []
    successful = 0
    failed = 0

    for i, (request, cached) in enumerate(zip(request_list.requests, cached_values)):
        if cached:
            responses.append(
                BatchAskResponse(
                    request_id=request.request_id,
                    success=True,
                    answer=cached.get("answer", ""),
                    processing_time_ms=0.0,
                    from_cache=True,
                )
            )
            successful += 1
        else:
            responses.append(
                BatchAskResponse(
                    request_id=request.request_id,
                    success=False,
                    answer="",
                    error="Query not pre-computed",
                    processing_time_ms=0.0,
                    from_cache=False,
                )
            )
            failed += 1

    total_time = (time.time() - start_time) * 1000

    logger.info(
        "precomputed_batch_completed",
        total_requests=len(request_list.requests),
        cache_hits=successful,
        cache_misses=failed,
        total_time_ms=round(total_time, 2),
    )

    return BatchAskResponseList(
        results=responses,
        total_requests=len(request_list.requests),
        successful_count=successful,
        failed_count=failed,
        total_processing_time_ms=round(total_time, 2),
        from_cache_count=successful,
    )
