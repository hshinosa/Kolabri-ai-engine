"""Coverage for chat reading-recommendations and fallback helpers."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import chat as chat_routes
from app.api.routes.chat import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_build_recommendation_fallback_shape():
    fb = chat_routes.build_recommendation_fallback()
    assert fb.success is True
    assert fb.recommendations == []
    assert fb.fallback is not None
    assert "materi relevan" in fb.fallback.message.lower()


@patch("app.api.routes.chat.get_rag_pipeline")
def test_reading_recommendations_returns_items(mock_rag):
    mock_vs = MagicMock()
    mock_vs.search = AsyncMock(
        return_value=[
            {
                "content": "Snippet about databases",
                "metadata": {"source": "db.pdf", "page": 4},
                "rerank_score": 0.9,
            }
        ]
    )
    mock_pipeline = MagicMock()
    mock_pipeline.vector_store = mock_vs
    mock_pipeline._format_search_results = MagicMock(
        side_effect=lambda raw: [
            {
                "content": r["content"],
                "metadata": r["metadata"],
                "rerank_score": r["rerank_score"],
            }
            for r in raw
        ]
    )
    mock_rag.return_value = mock_pipeline

    resp = client.post(
        "/reading-recommendations",
        json={"topic": "database", "course_id": "course_1", "limit": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["recommendations"]) == 1
    assert data["recommendations"][0]["page"] == 4


@patch("app.api.routes.chat.get_rag_pipeline")
def test_reading_recommendations_empty_results_use_fallback(mock_rag):
    mock_vs = MagicMock()
    mock_vs.search = AsyncMock(return_value=[])
    mock_pipeline = MagicMock()
    mock_pipeline.vector_store = mock_vs
    mock_pipeline._format_search_results = MagicMock(return_value=[])
    mock_rag.return_value = mock_pipeline

    resp = client.post(
        "/reading-recommendations",
        json={"topic": "obscure", "course_id": "c1", "limit": 3},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["recommendations"] == []
    assert data["fallback"] is not None


@patch("app.api.routes.chat.get_rag_pipeline")
def test_reading_recommendations_skips_low_score_and_empty_snippet(mock_rag):
    mock_vs = MagicMock()
    mock_vs.search = AsyncMock(
        return_value=[
            {"content": "   ", "metadata": {"source": "a"}, "score": 0.9},
            {"content": "good text", "metadata": {"source": "b"}, "score": 0.05},
        ]
    )
    mock_pipeline = MagicMock()
    mock_pipeline.vector_store = mock_vs
    mock_pipeline._format_search_results = MagicMock(
        side_effect=lambda raw: [
            {
                "content": r["content"],
                "metadata": r["metadata"],
                "score": r["score"],
            }
            for r in raw
        ]
    )
    mock_rag.return_value = mock_pipeline

    resp = client.post(
        "/reading-recommendations",
        json={"topic": "db", "course_id": "c1", "limit": 5},
    )
    assert resp.status_code == 200
    assert resp.json()["fallback"] is not None


@patch("app.api.routes.chat.get_rag_pipeline")
def test_reading_recommendations_respects_limit(mock_rag):
    rows = [
        {
            "content": f"snippet {i}",
            "metadata": {"source": f"src{i}"},
            "score": 0.5,
        }
        for i in range(5)
    ]
    mock_vs = MagicMock()
    mock_vs.search = AsyncMock(return_value=rows)
    mock_pipeline = MagicMock()
    mock_pipeline.vector_store = mock_vs
    mock_pipeline._format_search_results = MagicMock(side_effect=lambda raw: raw)
    mock_rag.return_value = mock_pipeline

    resp = client.post(
        "/reading-recommendations",
        json={"topic": "t", "course_id": "c1", "limit": 2},
    )
    assert len(resp.json()["recommendations"]) == 2


@patch(
    "app.api.routes.chat.get_rag_pipeline", side_effect=RuntimeError("pipeline down")
)
def test_reading_recommendations_internal_error(mock_rag):
    resp = client.post(
        "/reading-recommendations",
        json={"topic": "x", "course_id": "c1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["error"] == "Internal error"
    assert data["fallback"] is not None
