"""Coverage for personal-chat RAG scan breadth and transport parity.

Covers change `personal-chat-rag-coverage`:
- search_personal_rag scans every requested course up to the schema bound
  (not a hard 10-slice) and isolates per-collection failures.
- personal_chat_stream passes provider_context to retrieval, matching
  personal_chat.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())

from app.api.routes import chat as chat_routes
from app.api.routes.chat import MAX_PERSONAL_RAG_COURSES, search_personal_rag


def _hit(course_id: str, score: float) -> dict:
    return {
        "content": f"content for {course_id}",
        "metadata": {"source": f"{course_id}.pdf", "page": 1},
        "score": score,
    }


@pytest.mark.asyncio
async def test_search_scans_all_courses_beyond_old_ten_slice():
    """15 requested courses -> all 15 collections searched (old code capped 10)."""
    course_ids = [f"course-{i}" for i in range(15)]
    searched: list[str] = []

    async def fake_search(*, query, collection_name, n_results, score_threshold):
        searched.append(collection_name)
        cid = collection_name.removeprefix("course_")
        return [_hit(cid, 0.5)]

    mock_vs = MagicMock()
    mock_vs.search = AsyncMock(side_effect=fake_search)
    mock_pipeline = MagicMock()
    mock_pipeline.vector_store = mock_vs

    with patch(
        "app.api.routes.chat.get_rag_pipeline", return_value=mock_pipeline
    ):
        results = await search_personal_rag("query", course_ids)

    assert len(searched) == 15
    assert set(searched) == {f"course_{cid}" for cid in course_ids}
    # top-7 merge cap still applied
    assert len(results) == 7


@pytest.mark.asyncio
async def test_search_respects_schema_upper_bound():
    """More than the bound -> truncated to MAX_PERSONAL_RAG_COURSES collections."""
    course_ids = [f"course-{i}" for i in range(MAX_PERSONAL_RAG_COURSES + 5)]
    searched: list[str] = []

    async def fake_search(*, query, collection_name, n_results, score_threshold):
        searched.append(collection_name)
        return []

    mock_vs = MagicMock()
    mock_vs.search = AsyncMock(side_effect=fake_search)
    mock_pipeline = MagicMock()
    mock_pipeline.vector_store = mock_vs

    with patch(
        "app.api.routes.chat.get_rag_pipeline", return_value=mock_pipeline
    ):
        await search_personal_rag("query", course_ids)

    assert len(searched) == MAX_PERSONAL_RAG_COURSES


@pytest.mark.asyncio
async def test_search_isolates_failing_collection():
    """One collection raising does not abort the batch; others still merge."""
    course_ids = ["good-a", "bad", "good-b"]

    async def fake_search(*, query, collection_name, n_results, score_threshold):
        if collection_name == "course_bad":
            raise RuntimeError("collection unavailable")
        cid = collection_name.removeprefix("course_")
        return [_hit(cid, 0.6)]

    mock_vs = MagicMock()
    mock_vs.search = AsyncMock(side_effect=fake_search)
    mock_pipeline = MagicMock()
    mock_pipeline.vector_store = mock_vs

    with patch(
        "app.api.routes.chat.get_rag_pipeline", return_value=mock_pipeline
    ):
        results = await search_personal_rag("query", course_ids)

    sources = {r["metadata"]["source"] for r in results}
    assert sources == {"good-a.pdf", "good-b.pdf"}
    assert all("bad" not in s for s in sources)


def test_personal_chat_stream_passes_provider_context_to_rag():
    """Stream endpoint forwards resolved provider_context into retrieval."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(chat_routes.router)
    client = TestClient(app)

    captured = {}

    async def fake_rag(message, course_ids, provider_context=None):
        captured["provider_context"] = provider_context
        return []

    mock_llm = MagicMock()
    mock_llm.model = "gpt-test"
    mock_llm.client.chat.completions.create = AsyncMock(return_value=iter([]))

    sentinel = object()

    with patch(
        "app.api.routes.chat.resolve_provider_context", return_value=sentinel
    ), patch(
        "app.api.routes.chat.get_llm_service", return_value=mock_llm
    ), patch(
        "app.api.routes.chat.search_personal_rag", side_effect=fake_rag
    ):
        client.post(
            "/chat/personal/stream",
            json={"message": "hai", "course_ids": ["c1"], "history": []},
        )

    assert captured["provider_context"] is sentinel
