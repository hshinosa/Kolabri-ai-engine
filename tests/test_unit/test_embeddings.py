"""Tests for Gemini embedding service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import embeddings
from app.services.embeddings import GeminiEmbeddingService, get_embedding_service


@pytest.fixture
def mock_async_client():
    client = MagicMock()
    client.post = AsyncMock()
    return client


@pytest.fixture
def configured_service(mock_async_client):
    with patch("app.services.embeddings.httpx.AsyncClient", return_value=mock_async_client):
        with patch.object(embeddings.settings, "GEMINI_API_KEY", "gemini-test-key"), patch.object(
            embeddings.settings, "GOOGLE_API_KEY", ""
        ), patch.object(
            embeddings.settings,
            "GEMINI_EMBEDDING_MODEL",
            "models/text-embedding-004",
        ):
            service = GeminiEmbeddingService()
            service.initialize()
            yield service


def _mock_response(payload):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    return response


class TestGeminiEmbeddingService:
    def test_init(self):
        service = GeminiEmbeddingService()

        assert service._initialized is False
        assert service._api_key is None
        assert service._model is None
        assert service._client is None

    def test_initialize(self, mock_async_client):
        with patch("app.services.embeddings.httpx.AsyncClient", return_value=mock_async_client):
            with patch.object(embeddings.settings, "GEMINI_API_KEY", "gemini-test-key"), patch.object(
                embeddings.settings, "GOOGLE_API_KEY", ""
            ), patch.object(
                embeddings.settings,
                "GEMINI_EMBEDDING_MODEL",
                "models/text-embedding-004",
            ):
                service = GeminiEmbeddingService()
                service.initialize()

        assert service._initialized is True
        assert service._api_key == "gemini-test-key"
        assert service._model == "models/text-embedding-004"
        assert service._client is mock_async_client

    def test_initialize_uses_google_api_key_fallback(self, mock_async_client):
        with patch("app.services.embeddings.httpx.AsyncClient", return_value=mock_async_client):
            with patch.object(embeddings.settings, "GEMINI_API_KEY", ""), patch.object(
                embeddings.settings, "GOOGLE_API_KEY", "google-fallback-key"
            ), patch.object(
                embeddings.settings,
                "GEMINI_EMBEDDING_MODEL",
                "models/text-embedding-004",
            ):
                service = GeminiEmbeddingService()
                service.initialize()

        assert service._api_key == "google-fallback-key"

    def test_initialize_no_api_key(self):
        with patch.object(embeddings.settings, "GEMINI_API_KEY", ""), patch.object(
            embeddings.settings, "GOOGLE_API_KEY", ""
        ):
            service = GeminiEmbeddingService()

            with pytest.raises(ValueError, match="GEMINI_API_KEY or GOOGLE_API_KEY is required"):
                service.initialize()

    def test_initialize_already_initialized(self, configured_service):
        original_client = configured_service._client

        configured_service.initialize()

        assert configured_service._client is original_client

    def test_ensure_initialized_calls_initialize(self):
        service = GeminiEmbeddingService()
        service.initialize = MagicMock()

        service._ensure_initialized()

        service.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_text(self, configured_service, mock_async_client):
        mock_async_client.post.return_value = _mock_response(
            {"embedding": {"values": [0.1, 0.2, 0.3]}}
        )

        result = await configured_service.embed_text("Test text")

        assert result == [0.1, 0.2, 0.3]
        mock_async_client.post.assert_awaited_once_with(
            "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent",
            params={"key": "gemini-test-key"},
            json={
                "model": "models/text-embedding-004",
                "content": {"parts": [{"text": "Test text"}]},
            },
        )

    @pytest.mark.asyncio
    async def test_embed_texts(self, configured_service, mock_async_client):
        mock_async_client.post.return_value = _mock_response(
            {"embeddings": [{"values": [0.1, 0.2]}, {"values": [0.3, 0.4]}]}
        )

        result = await configured_service.embed_texts(["Text 1", "Text 2"])

        assert result == [[0.1, 0.2], [0.3, 0.4]]
        mock_async_client.post.assert_awaited_once_with(
            "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:batchEmbedContents",
            params={"key": "gemini-test-key"},
            json={
                "requests": [
                    {
                        "model": "models/text-embedding-004",
                        "content": {"parts": [{"text": "Text 1"}]},
                    },
                    {
                        "model": "models/text-embedding-004",
                        "content": {"parts": [{"text": "Text 2"}]},
                    },
                ]
            },
        )

    @pytest.mark.asyncio
    async def test_embed_query(self, configured_service, mock_async_client):
        mock_async_client.post.return_value = _mock_response(
            {"embedding": {"values": [0.9, 0.8, 0.7]}}
        )

        result = await configured_service.embed_query("Test query")

        assert result == [0.9, 0.8, 0.7]
        mock_async_client.post.assert_awaited_once_with(
            "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent",
            params={"key": "gemini-test-key"},
            json={
                "model": "models/text-embedding-004",
                "content": {"parts": [{"text": "Test query"}]},
                "taskType": "RETRIEVAL_QUERY",
            },
        )

    @pytest.mark.asyncio
    async def test_get_embedding(self, configured_service):
        with patch.object(configured_service, "embed_text", new=AsyncMock(return_value=[0.5, 0.6])) as mock_embed:
            result = await configured_service.get_embedding("alias text")

        assert result == [0.5, 0.6]
        mock_embed.assert_awaited_once_with("alias text")


class TestGetEmbeddingService:
    def test_get_embedding_service_singleton(self):
        embeddings._embedding_service = None

        service1 = get_embedding_service()
        service2 = get_embedding_service()

        assert service1 is service2
        assert isinstance(service1, GeminiEmbeddingService)

    def test_get_embedding_service_returns_existing_instance(self):
        existing = GeminiEmbeddingService()
        embeddings._embedding_service = existing

        result = get_embedding_service()

        assert result is existing
