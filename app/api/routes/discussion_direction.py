"""
Discussion direction: relevance classification and session summary (NFR-USABILITY-04).
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.schemas import ProviderContextV1
from app.core.config import settings
from app.core.logging import get_logger
from app.services.llm import get_llm_service

logger = get_logger(__name__)

router = APIRouter(tags=["Discussion Direction"])


def _dump_provider_context(
    provider_context: Optional[ProviderContextV1],
) -> Optional[dict[str, Any]]:
    if provider_context is None:
        return None
    return provider_context.model_dump(exclude_none=True)


def _resolve_provider_context(
    provider_context: Optional[ProviderContextV1],
) -> Optional[dict[str, Any]]:
    if not settings.UNIFIED_PROVIDER_ENABLED:
        return None
    if settings.UNIFIED_PROVIDER_ORCHESTRATION:
        return _dump_provider_context(provider_context)
    return _dump_provider_context(provider_context)


class ClassifyMessageItem(BaseModel):
    id: str
    content: str


class ClassifyRelevanceRequest(BaseModel):
    messages: list[ClassifyMessageItem]
    goal: str
    provider_context: Optional[ProviderContextV1] = None


class ClassifyRelevanceResponse(BaseModel):
    classifications: list[dict[str, Any]]


class SessionSummaryMessage(BaseModel):
    content: str
    senderName: str = Field(default="Peserta")


class SessionSummaryStats(BaseModel):
    totalMessages: int = 0
    participantCount: int = 0


class SessionSummaryRequest(BaseModel):
    messages: list[SessionSummaryMessage]
    goal: str
    stats: SessionSummaryStats = Field(default_factory=SessionSummaryStats)
    provider_context: Optional[ProviderContextV1] = None


class SessionSummaryResponse(BaseModel):
    goalAchieved: bool
    topics: list[str]
    contributions: dict[str, int]
    assessment: str


def _parse_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


@router.post("/classify-relevance", response_model=ClassifyRelevanceResponse)
async def classify_relevance(
    body: ClassifyRelevanceRequest,
) -> ClassifyRelevanceResponse:
    goal = (body.goal or "").strip()
    if not goal or not body.messages:
        return ClassifyRelevanceResponse(
            classifications=[
                {"messageId": m.id, "isRelevant": True} for m in body.messages
            ]
        )

    lines = "\n".join(
        f'- id: "{m.id}" | pesan: "{m.content[:500]}"' for m in body.messages
    )
    prompt = (
        f"Tujuan pembelajaran sesi:\n{goal}\n\n"
        f"Pesan diskusi:\n{lines}\n\n"
        "Untuk setiap pesan, tentukan apakah RELEVAN dengan tujuan (true/false). "
        "Balas HANYA JSON valid: "
        '{"classifications":[{"messageId":"<id>","isRelevant":true|false},...]}'
    )

    llm = get_llm_service(
        provider_context=_resolve_provider_context(body.provider_context)
    )
    result = await llm.generate(
        prompt=prompt,
        system_prompt=(
            "Kamu menilai relevansi pesan diskusi kelompok terhadap tujuan pembelajaran. "
            "Jawab hanya JSON, tanpa markdown."
        ),
        temperature=0.1,
    )

    classifications: list[dict[str, Any]] = []
    if result.success and result.content:
        parsed = _parse_json_object(result.content)
        if parsed and isinstance(parsed.get("classifications"), list):
            for item in parsed["classifications"]:
                if isinstance(item, dict) and "messageId" in item:
                    classifications.append(
                        {
                            "messageId": str(item["messageId"]),
                            "isRelevant": bool(item.get("isRelevant", True)),
                        }
                    )

    if len(classifications) != len(body.messages):
        by_id = {c["messageId"]: c["isRelevant"] for c in classifications}
        classifications = [
            {"messageId": m.id, "isRelevant": by_id.get(m.id, True)}
            for m in body.messages
        ]

    return ClassifyRelevanceResponse(classifications=classifications)


@router.post("/session-summary", response_model=SessionSummaryResponse)
async def session_summary(body: SessionSummaryRequest) -> SessionSummaryResponse:
    goal = (body.goal or "").strip() or "Tujuan tidak ditentukan"
    contributions: dict[str, int] = {}
    for m in body.messages:
        name = (m.senderName or "Peserta").strip() or "Peserta"
        contributions[name] = contributions.get(name, 0) + 1

    transcript = "\n".join(
        f"{m.senderName}: {m.content[:400]}" for m in body.messages[-40:]
    )
    stats = body.stats
    prompt = (
        f"Tujuan: {goal}\n"
        f"Total pesan: {stats.totalMessages}, peserta: {stats.participantCount}\n\n"
        f"Transkrip:\n{transcript or '(kosong)'}\n\n"
        "Buat ringkasan JSON dengan kunci: goalAchieved (boolean), topics (array string, max 5), "
        "contributions (object nama->jumlah pesan), assessment (string Bahasa Indonesia, 2-4 kalimat)."
    )

    llm = get_llm_service(
        provider_context=_resolve_provider_context(body.provider_context)
    )
    result = await llm.generate(
        prompt=prompt,
        system_prompt=(
            "Kamu merangkum diskusi kelompok untuk mahasiswa. "
            "Jawab hanya JSON valid tanpa markdown."
        ),
        temperature=0.3,
    )

    default = SessionSummaryResponse(
        goalAchieved=False,
        topics=[goal],
        contributions=contributions,
        assessment="Ringkasan tidak tersedia. Silakan coba lagi nanti.",
    )

    if not result.success or not result.content:
        return default

    parsed = _parse_json_object(result.content)
    if not parsed:
        return default

    topics = parsed.get("topics")
    if not isinstance(topics, list):
        topics = [goal]
    topics = [str(t) for t in topics[:5]]

    cont = parsed.get("contributions")
    if not isinstance(cont, dict):
        cont = contributions
    else:
        cont = {str(k): int(v) for k, v in cont.items() if isinstance(v, (int, float))}

    assessment = parsed.get("assessment")
    if not isinstance(assessment, str) or not assessment.strip():
        assessment = default.assessment

    return SessionSummaryResponse(
        goalAchieved=bool(parsed.get("goalAchieved", False)),
        topics=topics,
        contributions=cont,
        assessment=assessment,
    )
