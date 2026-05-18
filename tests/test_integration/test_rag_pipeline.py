import pytest
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from io import BytesIO


@pytest.fixture(scope="module")
def integration_app():
    @asynccontextmanager
    async def mock_lifespan(app: FastAPI):
        yield

    from app.api.routes import router as api_router

    app = FastAPI(title="Kolabri AI-Engine (Test)", version="1.0.0", lifespan=mock_lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api")
    return app


@pytest.fixture(scope="module")
def client(integration_app) -> TestClient:
    with TestClient(integration_app, raise_server_exceptions=False) as c:
        yield c


def _make_rag_result(answer="Test RAG response", sources=None, success=True):
    from app.services.rag import RAGResult
    return RAGResult(
        answer=answer, sources=sources or [], query="test query",
        tokens_used=50, success=success,
    )


class TestRAGAskEndpoint:
    def test_ask_question_success(self, client):
        with patch("app.api.routes.chat.get_rag_pipeline") as mock_get_rag:
            mock_rag = MagicMock()
            mock_rag.query = AsyncMock(return_value=_make_rag_result("Jawabannya adalah..."))
            mock_get_rag.return_value = mock_rag

            response = client.post("/api/ask", json={
                "query": "Apa itu machine learning?",
                "course_id": "course_cs101",
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "Jawabannya" in data["answer"]

    def test_ask_empty_query(self, client):
        response = client.post("/api/ask", json={
            "query": "",
            "course_id": "course_cs101",
        })
        assert response.status_code == 422


class TestRAGIngestEndpoint:
    def test_ingest_document_success(self, client):
        with (
            patch("app.api.routes.documents.get_document_processor") as mock_get_dp,
            patch("app.api.routes.documents.get_vector_store") as mock_get_vs,
        ):
            from app.services.document_processor import ProcessedDocument, ProcessedChunk
            chunks = [
                ProcessedChunk(text=f"Chunk {i}", metadata={"source": "test.pdf", "page": i}, chunk_id=f"c_{i}")
                for i in range(3)
            ]
            mock_dp = MagicMock()
            mock_dp.process = AsyncMock(return_value=ProcessedDocument(
                filename="test.pdf", file_type="pdf", chunks=chunks,
                page_count=3, image_count=0, total_characters=300,
                processing_time_ms=100.0, success=True,
            ))
            mock_get_dp.return_value = mock_dp

            mock_vs = MagicMock()
            mock_vs.add_documents = AsyncMock(return_value=True)
            mock_vs._ensure_collection = AsyncMock()
            mock_get_vs.return_value = mock_vs

            pdf_content = b"%PDF-1.4 fake content"
            response = client.post("/api/ingest", data={
                "course_id": "course_cs101",
                "file_id": "file-1",
            }, files={"file": ("test.pdf", BytesIO(pdf_content), "application/pdf")})

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True


class TestRAGDeleteEndpoint:
    def test_delete_document_success(self, client):
        with patch("app.api.routes.documents.get_vector_store") as mock_get_vs:
            mock_vs = MagicMock()
            mock_vs.delete_documents = AsyncMock(return_value=True)
            mock_get_vs.return_value = mock_vs

            response = client.delete("/api/documents/doc-123")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
