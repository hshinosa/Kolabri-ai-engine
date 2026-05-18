"""
RAG ask & personal chat endpoints.
"""

import json as _json
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.schemas import AskRequest, AskResponse, PersonalChatRequest, PersonalChatResponse
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
    "Jawab dalam Bahasa Indonesia kecuali diminta sebaliknya. "
    + PERSONAL_CHAT_STYLE
)

COURSE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


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

        rag_pipeline = get_rag_pipeline()

        collection_name = f"course_{request.course_id}"

        result = await rag_pipeline.query(
            query=request.query, collection_name=collection_name, n_results=5
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
    "/chat/personal",
    response_model=PersonalChatResponse,
    tags=["Core-API Integration"],
    summary="Personal AI chat (multi-turn, no RAG)",
)
async def personal_chat(request: PersonalChatRequest):
    try:
        llm = get_llm_service()

        messages = [
            {"role": "system", "content": PERSONAL_CHAT_SYSTEM_PROMPT},
        ]

        for msg in request.history[-20:]:
            messages.append({"role": msg.role, "content": msg.content})

        messages.append({"role": "user", "content": request.message})

        response = await llm.client.chat.completions.create(
            model=llm.model,
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
        )

        reply = response.choices[0].message.content.strip()

        return PersonalChatResponse(reply=reply, success=True)

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
    summary="Personal AI chat with SSE streaming",
)
async def personal_chat_stream(request: PersonalChatRequest):
    llm = get_llm_service()

    messages = [
        {"role": "system", "content": PERSONAL_CHAT_SYSTEM_PROMPT},
    ]

    for msg in request.history[-20:]:
        messages.append({"role": msg.role, "content": msg.content})

    messages.append({"role": "user", "content": request.message})

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
            yield "data: [DONE]\n\n"
        except Exception:
            logger.exception("personal_chat_stream_failed")
            yield f"data: {_json.dumps({'error': 'Internal error'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
