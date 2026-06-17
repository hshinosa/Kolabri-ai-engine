"""
RAG ask & personal chat endpoints.
"""

import json as _json
import re
from typing import Any, cast

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from openai.types.chat import ChatCompletionMessageParam

from app.api.schemas import (
    AskRequest,
    AskResponse,
    PersonalChatRequest,
    PersonalChatResponse,
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

router = APIRouter()

PERSONAL_CHAT_SYSTEM_PROMPT = (
    "Kamu adalah Kolabri AI, asisten belajar cerdas untuk mahasiswa. "
    "Bantu mahasiswa memahami materi, menjawab pertanyaan akademik maupun pertanyaan personal ringan dengan penjelasan yang jelas, akurat, suportif, dan edukatif. "
    "Jawab dalam Bahasa Indonesia kecuali diminta sebaliknya. " + PERSONAL_CHAT_STYLE
)

COURSE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
MIN_RELEVANCE_SCORE = 0.15


def dump_provider_context(provider_context: Any) -> dict[str, Any] | None:
    if provider_context is None:
        return None
    if hasattr(provider_context, "model_dump"):
        return provider_context.model_dump(exclude_none=True)
    return provider_context


def resolve_provider_context(
    provider_context: Any, feature_flag: bool
) -> dict[str, Any] | None:
    if not settings.UNIFIED_PROVIDER_ENABLED:
        return None
    if feature_flag:
        return dump_provider_context(provider_context)
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
            provider_context=resolve_provider_context(
                request.provider_context,
                settings.UNIFIED_PROVIDER_RAG,
            )
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
        else:
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
            provider_context=resolve_provider_context(
                request.provider_context,
                settings.UNIFIED_PROVIDER_RAG,
            )
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
    "Gunakan materi di atas sebagai referensi utama untuk menjawab. "
    "Jika materi tidak mencakup pertanyaan, jawab berdasarkan pengetahuan umum tetapi jelaskan bahwa itu bukan dari materi kuliah."
)

CITATION_INSTRUCTION = (
    "\n\nJika kamu menggunakan materi di atas, sebutkan sumbernya secara singkat "
    "(contoh: 'Berdasarkan materi [nama file]...'). "
    "Jangan mengarang sumber yang tidak ada di daftar referensi."
)


async def search_personal_rag(
    query: str,
    course_ids: list[str],
    top_k_per_course: int = 3,
    provider_context=None,
) -> list[dict]:
    """Search across multiple course collections and merge results."""
    rag_pipeline = get_rag_pipeline(provider_context=provider_context)
    all_results = []

    for course_id in course_ids[:10]:
        collection_name = f"course_{course_id}"
        try:
            results = await rag_pipeline.vector_store.search(
                query=query,
                collection_name=collection_name,
                n_results=top_k_per_course,
                score_threshold=0.35,
            )
            for r in results:
                r["_course_id"] = course_id
            all_results.extend(results)
        except Exception:
            logger.warning(
                "personal_rag_collection_skip",
                collection=collection_name,
            )

    all_results.sort(key=lambda r: r.get("score", 0), reverse=True)
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
    "/chat/personal",
    response_model=PersonalChatResponse,
    tags=["Core-API Integration"],
    summary="Personal AI chat with RAG across enrolled courses",
)
async def personal_chat(request: PersonalChatRequest):
    try:
        llm = get_llm_service(
            provider_context=resolve_provider_context(
                request.provider_context,
                settings.UNIFIED_PROVIDER_PERSONAL_CHAT,
            )
        )

        system_prompt = PERSONAL_CHAT_SYSTEM_PROMPT
        citations = []

        if request.course_ids:
            resolved_ctx = resolve_provider_context(
                request.provider_context,
                settings.UNIFIED_PROVIDER_PERSONAL_CHAT,
            )
            rag_results = await search_personal_rag(
                request.message,
                request.course_ids,
                provider_context=resolved_ctx,
            )
            if rag_results:
                context_str, citations = build_rag_context_and_citations(rag_results)
                system_prompt += RAG_CONTEXT_PROMPT.format(context=context_str)
                system_prompt += CITATION_INSTRUCTION

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt},
        ]

        for msg in request.history[-20:]:
            messages.append(
                cast(
                    ChatCompletionMessageParam,
                    cast(Any, {"role": msg.role, "content": msg.content}),
                )
            )

        messages.append(
            cast(
                ChatCompletionMessageParam,
                cast(Any, {"role": "user", "content": request.message}),
            )
        )

        response = await llm.client.chat.completions.create(
            model=llm.model,
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
        )

        reply = (response.choices[0].message.content or "").strip()

        return PersonalChatResponse(
            reply=reply,
            success=True,
            citations=citations,
        )

    except Exception:
        logger.exception("personal_chat_failed")
        return PersonalChatResponse(
            reply="Maaf, terjadi kesalahan. Silakan coba lagi.",
            success=False,
            error="Internal error",
        )


@router.post(
    "/chat/personal/stream",
    tags=["Core-API Integration"],
    summary="Personal AI chat with RAG and SSE streaming",
)
async def personal_chat_stream(request: PersonalChatRequest):
    llm = get_llm_service(
        provider_context=resolve_provider_context(
            request.provider_context,
            settings.UNIFIED_PROVIDER_PERSONAL_CHAT,
        )
    )

    system_prompt = PERSONAL_CHAT_SYSTEM_PROMPT
    citations = []

    if request.course_ids:
        rag_results = await search_personal_rag(request.message, request.course_ids)
        if rag_results:
            context_str, citations = build_rag_context_and_citations(rag_results)
            system_prompt += RAG_CONTEXT_PROMPT.format(context=context_str)
            system_prompt += CITATION_INSTRUCTION

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
    ]

    for msg in request.history[-20:]:
        messages.append(
            cast(
                ChatCompletionMessageParam,
                cast(Any, {"role": msg.role, "content": msg.content}),
            )
        )

    messages.append(
        cast(
            ChatCompletionMessageParam,
            cast(Any, {"role": "user", "content": request.message}),
        )
    )

    async def event_generator():
        try:
            stream = await llm.client.chat.completions.create(
                model=llm.model,
                messages=messages,
                temperature=0.7,
                max_tokens=2048,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield f"data: {_json.dumps({'content': delta.content})}\n\n"

            if citations:
                yield f"data: {_json.dumps({'citations': citations})}\n\n"

            yield "data: [DONE]\n\n"
        except Exception:
            logger.exception("personal_chat_stream_failed")
            yield f"data: {_json.dumps({'error': 'Internal error'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
