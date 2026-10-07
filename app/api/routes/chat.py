"""
RAG ask & personal chat endpoints.
"""

import asyncio
import hashlib
import json as _json
import re
import weakref
from typing import Any, cast

from cachetools import TTLCache
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from openai.types.chat import ChatCompletionMessageParam

from app.api.schemas import (
    AskRequest,
    AskResponse,
    PersonalChatRequest,
    ReadingRecommendationFallback,
    ReadingRecommendationItem,
    ReadingRecommendationRequest,
    ReadingRecommendationResponse,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.core.prompt_styles import PERSONAL_CHAT_STYLE
from app.services.llm import get_llm_service
from app.services.rag import get_rag_pipeline

logger = get_logger(__name__)
from app.services.week_rag import rank_week_boosted_results

router = APIRouter()

PERSONAL_CHAT_SYSTEM_PROMPT = (
    "Kamu adalah Kolabri AI, asisten belajar cerdas untuk mahasiswa. "
    "Jawab dalam Bahasa Indonesia kecuali diminta sebaliknya. "
    "Ketika mahasiswa bertanya tentang materi atau topik kuliah, berikan jawaban yang SINGKAT dan SIMPEL. "
    "Fokus pada overview: minggu berapa saja materi tersebut dibahas, di kelas apa, dan poin utamanya secara singkat. "
    "JANGAN jabarkan semua detail materi. Cukup berikan gambaran besar agar mahasiswa tahu apa yang tersedia. "
    "Jika mereka ingin detail lebih lanjut, mereka bisa bertanya lagi secara spesifik. "
    "Untuk pertanyaan personal ringan, tetap ramah dan suportif. "
    "Gunakan bullet points hanya jika membantu keterbacaan, tapi jangan berlebihan. "
    + PERSONAL_CHAT_STYLE
)

PERSONAL_CHAT_TEMPERATURE = 0.7
PERSONAL_CHAT_MAX_TOKENS = 8192

COURSE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
MIN_RELEVANCE_SCORE = 0.15
# Upper bound on course collections scanned per personal-chat request.
# Matches PersonalChatRequest.course_ids max_length in app/api/schemas.py.
MAX_PERSONAL_RAG_COURSES = 20

# Chunk-replay cache + single-flight guards for /chat/personal/stream
# (TTLCache pattern from services/model_discovery.py): an identical request
# replays the recorded SSE payload instead of paying another provider
# round-trip, and concurrent identical requests wait for the in-flight leader
# instead of fanning out. State is scoped to the event loop serving the
# request — asyncio.Event is loop-affine, and a worker loop outlives every
# request, so in production the cache spans the process lifetime while
# per-request test loops stay isolated.
STREAM_CACHE_TTL_SECONDS = 600
_stream_state: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, tuple[TTLCache, dict[str, asyncio.Event]]
] = weakref.WeakKeyDictionary()


def _get_stream_state() -> tuple[TTLCache, dict[str, asyncio.Event]]:
    loop = asyncio.get_running_loop()
    state = _stream_state.get(loop)
    if state is None:
        state = (TTLCache(maxsize=256, ttl=STREAM_CACHE_TTL_SECONDS), {})
        _stream_state[loop] = state
    return state


def build_stream_cache_key(
    model: str,
    system_prompt: str,
    history: list[Any],
    user_content: str,
) -> str:
    """SHA-256 over every input that changes the provider response."""
    key_material = _json.dumps(
        {
            "model": model,
            "system": system_prompt,
            "history": [{"role": m.role, "content": m.content} for m in history],
            "user": user_content,
            "temperature": PERSONAL_CHAT_TEMPERATURE,
            "max_tokens": PERSONAL_CHAT_MAX_TOKENS,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(key_material.encode("utf-8")).hexdigest()


def dump_provider_context(provider_context: Any) -> dict[str, Any] | None:
    if provider_context is None:
        return None
    if hasattr(provider_context, "model_dump"):
        return provider_context.model_dump(exclude_none=True)
    return provider_context


def resolve_provider_context(provider_context: Any) -> dict[str, Any] | None:
    if not settings.UNIFIED_PROVIDER_ENABLED:
        return None
    return dump_provider_context(provider_context)


def build_recommendation_fallback() -> ReadingRecommendationResponse:
    return ReadingRecommendationResponse(
        success=True,
        recommendations=[],
        fallback=ReadingRecommendationFallback(
            message="Belum ada materi relevan yang siap direkomendasikan untuk topik ini.",
            suggestedNextStep="Persempit topik atau minta dosen mengunggah materi tambahan ke knowledge base course ini.",
        ),
    )


def validate_course_id(course_id: str) -> str:
    if not course_id or not COURSE_ID_PATTERN.match(course_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid course ID format. Only alphanumeric characters, underscores, and hyphens are allowed.",
        )
    return course_id


@router.post(
    "/ask",
    response_model=AskResponse,
    tags=["Core-API Integration"],
    summary="Answer question using RAG (for chat @AI mention)",
)
async def ask_question(request: AskRequest):
    try:
        validate_course_id(request.course_id)

        rag_pipeline = get_rag_pipeline(
            provider_context=resolve_provider_context(request.provider_context)
        )

        collection_name = f"course_{request.course_id}"

        result = await rag_pipeline.query(
            query=request.query,
            collection_name=collection_name,
            n_results=settings.TOP_K_RESULTS,
            guardrail_context={"guardrail_policy": request.guardrail_policy or {}},
        )

        if result.success:
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

            return AskResponse(answer=answer, success=True)
        return AskResponse(
            answer="Maaf, saya tidak bisa menemukan jawaban untuk pertanyaan tersebut dalam materi kuliah.",
            success=False,
            error=result.error,
        )

    except Exception:
        logger.exception("ask_question_failed", query=request.query[:100])
        return AskResponse(
            answer="Maaf, terjadi kesalahan saat memproses pertanyaan. Silakan coba lagi.",
            success=False,
            error="Internal error",
        )


@router.post(
    "/reading-recommendations",
    response_model=ReadingRecommendationResponse,
    tags=["Core-API Integration"],
    summary="Structured reading recommendations from course knowledge base",
)
async def get_reading_recommendations(request: ReadingRecommendationRequest):
    try:
        validate_course_id(request.course_id)

        rag_pipeline = get_rag_pipeline(
            provider_context=resolve_provider_context(request.provider_context)
        )
        collection_name = f"course_{request.course_id}"
        raw_results = await rag_pipeline.vector_store.search(
            query=request.topic,
            collection_name=collection_name,
            n_results=max(request.limit * 2, request.limit),
            where={"course_id": request.course_id},
        )
        results = rag_pipeline._format_search_results(raw_results)

        recommendations = []
        seen_sources = set()
        for result in results:
            metadata = result.get("metadata", {})
            source_title = (
                metadata.get("source") or metadata.get("filename") or "Dokumen Course"
            )
            relevance_score = float(
                result.get("rerank_score") or result.get("score") or 0
            )

            if relevance_score < MIN_RELEVANCE_SCORE or source_title in seen_sources:
                continue

            snippet = (result.get("content") or "").strip().replace("\n", " ")[:240]
            if not snippet:
                continue

            page = metadata.get("page")
            recommendations.append(
                ReadingRecommendationItem(
                    source_title=source_title,
                    snippet=snippet,
                    rationale=f"Materi ini paling dekat dengan topik '{request.topic}' berdasarkan pencarian di knowledge base course.",
                    suggested_action=(
                        f"Baca bagian ini{' di halaman ' + str(page) if page else ''}, lalu ringkas 2 poin penting yang paling relevan dengan topik {request.topic}."
                    ),
                    page=page,
                    relevance_score=relevance_score,
                )
            )
            seen_sources.add(source_title)

            if len(recommendations) >= request.limit:
                break

        if not recommendations:
            return build_recommendation_fallback()

        return ReadingRecommendationResponse(
            success=True, recommendations=recommendations, fallback=None
        )
    except Exception:
        logger.exception("reading_recommendations_failed", topic=request.topic[:100])
        return ReadingRecommendationResponse(
            success=False,
            recommendations=[],
            fallback=build_recommendation_fallback().fallback,
            error="Internal error",
        )


RAG_CONTEXT_PROMPT = (
    "\n\nBerikut adalah materi kuliah yang relevan dari knowledge base:\n\n"
    "{context}\n\n"
    "Gunakan materi di atas sebagai konteks, tapi JANGAN jabarkan semua detail. "
    "Berikan jawaban SINGKAT yang fokus pada: "
    "1) Topik/materi apa saja yang tersedia, "
    "2) Di minggu berapa materi tersebut dibahas, "
    "3) Di kelas mana materi ini relevan. "
    "Jika pertanyaan tidak terjawab oleh materi di atas, katakan dengan jujur bahwa materi tidak mencakup pertanyaan tersebut."
)
CITATION_INSTRUCTION = (
    " Ketika merujuk materi, sebutkan secara singkat (contoh: 'materi minggu 3 di Pemrograman Web')."
    " Jangan membuat sitasi yang terlalu panjang atau detail."
)


async def search_personal_rag(
    query: str,
    course_ids: list[str],
    top_k_per_course: int = 3,
    provider_context=None,
    week_index: int | None = None,
    focus_course_id: str | None = None,
) -> list[dict]:
    """Search across multiple course collections and merge results.

    week_index: boost chunk minggu terpilih (rank_week_boosted_results —
    chunk minggu lain tetap boleh ikut, hanya di bawah margin skor).
    focus_course_id: persempit pencarian ke satu koleksi kursus.
    """
    rag_pipeline = get_rag_pipeline(provider_context=provider_context)

    # Scan up to the schema-advertised bound (PersonalChatRequest.course_ids
    # max_length=20). Search collections concurrently so widening the scan
    # does not multiply latency.
    if focus_course_id:
        scanned = [focus_course_id]
    else:
        scanned = course_ids[:MAX_PERSONAL_RAG_COURSES]

    # Saat fokus minggu, ambil lebih banyak kandidat supaya boost punya bahan
    n_results = top_k_per_course * 3 if week_index is not None else top_k_per_course

    async def _search_one(course_id: str) -> list[dict]:
        collection_name = f"course_{course_id}"
        try:
            results = await rag_pipeline.vector_store.search(
                query=query,
                collection_name=collection_name,
                n_results=n_results,
                score_threshold=0.35,
            )
            for r in results:
                r["_course_id"] = course_id
            return results
        except Exception:
            logger.warning(
                "personal_rag_collection_skip",
                collection=collection_name,
            )
            return []

    per_course = await asyncio.gather(*(_search_one(cid) for cid in scanned))
    all_results = [r for results in per_course for r in results]

    all_results.sort(key=lambda r: r.get("score", 0), reverse=True)
    if week_index is not None:
        all_results = rank_week_boosted_results(all_results, week_index)
    return all_results[:7]


def build_rag_context_and_citations(
    results: list[dict],
) -> tuple[str, list[dict]]:
    """Build context string and citation list from search results."""
    if not results:
        return "", []

    context_parts = []
    citations = []
    seen_sources = set()

    for i, r in enumerate(results, 1):
        content = (r.get("content") or "").strip()[:500]
        metadata = r.get("metadata") or {}
        source = metadata.get("source") or metadata.get("filename") or "Dokumen"
        page = metadata.get("page")
        course_id = r.get("_course_id", "")
        course_material_id = metadata.get("course_material_id")

        context_parts.append(
            f"[{i}] {source}{f' (hal. {page})' if page else ''}:\n{content}"
        )

        source_key = f"{source}:{page}"
        if source_key not in seen_sources:
            seen_sources.add(source_key)
            citations.append(
                {
                    "source": source,
                    "page": page,
                    "snippet": content[:150],
                    "course_id": course_id,
                    "course_material_id": course_material_id,
                }
            )

    return "\n\n".join(context_parts), citations


@router.post(
    "/chat/personal/stream",
    tags=["Core-API Integration"],
    summary="Personal AI chat with RAG and SSE streaming",
)
async def personal_chat_stream(request: PersonalChatRequest):
    resolved_ctx = resolve_provider_context(request.provider_context)
    llm = get_llm_service(provider_context=resolved_ctx)

    # Prefix-cache friendly layout (DeepSeek/OpenAI prompt caching): the
    # system prompt stays byte-identical across requests; the dynamic RAG
    # context leads the user turn instead of being appended to the system
    # prompt, where it would invalidate the provider's cached prefix.
    system_prompt = PERSONAL_CHAT_SYSTEM_PROMPT
    citations = []
    context_block = ""

    if request.course_ids:
        rag_results = await search_personal_rag(
            request.message,
            request.course_ids,
            provider_context=resolved_ctx,
            week_index=request.week_index,
            focus_course_id=request.focus_course_id,
        )
        if rag_results:
            context_str, citations = build_rag_context_and_citations(rag_results)
            context_block = RAG_CONTEXT_PROMPT.format(context=context_str)
            context_block += CITATION_INSTRUCTION

    user_content = (
        f"{context_block}\n\n{request.message}" if context_block else request.message
    )

    history = request.history[-20:]
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
    ]

    for msg in history:
        messages.append(
            cast(
                ChatCompletionMessageParam,
                cast(Any, {"role": msg.role, "content": msg.content}),
            )
        )

    messages.append(
        cast(
            ChatCompletionMessageParam,
            cast(Any, {"role": "user", "content": user_content}),
        )
    )

    def sse(payload: dict) -> str:
        return f"data: {_json.dumps(payload)}\n\n"

    async def event_generator():
        try:
            await llm.ensure_ready()
            cache_key = build_stream_cache_key(
                model=llm.model,
                system_prompt=system_prompt,
                history=history,
                user_content=user_content,
            )

            # Replay an identical completed stream without another provider
            # round-trip; a concurrent identical request waits for the
            # in-flight leader instead of fanning out.
            chunk_cache, inflight = _get_stream_state()
            while True:
                cached_events = chunk_cache.get(cache_key)
                if cached_events is not None:
                    logger.info(
                        "llm_prompt_cache", result="hit", cache_key=cache_key[:16]
                    )
                    for event in cached_events:
                        yield sse(event)
                    yield "data: [DONE]\n\n"
                    return
                pending = inflight.get(cache_key)
                if pending is not None:
                    await pending.wait()
                    continue
                break

            logger.info("llm_prompt_cache", result="miss", cache_key=cache_key[:16])
            leader = asyncio.Event()
            inflight[cache_key] = leader
            collected: list[dict] = []
            try:
                stream = await llm.client.chat.completions.create(
                    model=llm.model,
                    messages=messages,
                    temperature=PERSONAL_CHAT_TEMPERATURE,
                    max_tokens=PERSONAL_CHAT_MAX_TOKENS,
                    stream=True,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        event = {"content": delta.content}
                        collected.append(event)
                        yield sse(event)

                if citations:
                    event = {"citations": citations}
                    collected.append(event)
                    yield sse(event)

                # Only completed streams enter the cache; failures never do.
                chunk_cache[cache_key] = collected
            finally:
                inflight.pop(cache_key, None)
                leader.set()

            yield "data: [DONE]\n\n"
        except Exception:
            logger.exception("personal_chat_stream_failed")
            yield f"data: {_json.dumps({'error': 'Internal error'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
