"""Additional coverage tests for Gemini embedding service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import embeddings
from app.services.embeddings import GeminiEmbeddingService, get_embedding_service


def _mock_response(payload):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    return response


class TestGeminiEmbeddingServiceFull:
    def test_initialize_already_initialized(self):
        service = GeminiEmbeddingService()
        existing_client = MagicMock()
        service._initialized = True
        service._client = existing_client

        service.initialize()

        assert service._client is existing_client

    @pytest.mark.asyncio
    async def test_embed_text_auto_init(self):
        service = GeminiEmbeddingService()
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=_mock_response({"embedding": {"values": [0.1, 0.2]}}))

        with patch("app.services.embeddings.httpx.AsyncClient", return_value=mock_client):
            with patch.object(embeddings.settings, "GEMINI_API_KEY", "gemini-test-key"), patch.object(
                embeddings.settings, "GOOGLE_API_KEY", ""
            ), patch.object(
                embeddings.settings,
                "GEMINI_EMBEDDING_MODEL",
                "models/text-embedding-004",
            ):
                result = await service.embed_text("test")

        assert result == [0.1, 0.2]
        assert service._initialized is True

    @pytest.mark.asyncio
    async def test_embed_texts_auto_init(self):
        service = GeminiEmbeddingService()
        mock_client = MagicMock()
        mock_client.post = AsyncMock(
            return_value=_mock_response({"embeddings": [{"values": [0.1, 0.2]}]})
        )

        with patch("app.services.embeddings.httpx.AsyncClient", return_value=mock_client):
            with patch.object(embeddings.settings, "GEMINI_API_KEY", "gemini-test-key"), patch.object(
                embeddings.settings, "GOOGLE_API_KEY", ""
            ), patch.object(
                embeddings.settings,
                "GEMINI_EMBEDDING_MODEL",
                "models/text-embedding-004",
            ):
                result = await service.embed_texts(["test"])

        assert result == [[0.1, 0.2]]

    @pytest.mark.asyncio
    async def test_embed_query_auto_init(self):
        service = GeminiEmbeddingService()
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=_mock_response({"embedding": {"values": [0.5, 0.6]}}))

        with patch("app.services.embeddings.httpx.AsyncClient", return_value=mock_client):
            with patch.object(embeddings.settings, "GEMINI_API_KEY", "gemini-test-key"), patch.object(
                embeddings.settings, "GOOGLE_API_KEY", ""
            ), patch.object(
                embeddings.settings,
                "GEMINI_EMBEDDING_MODEL",
                "models/text-embedding-004",
            ):
                result = await service.embed_query("query")

        assert result == [0.5, 0.6]

    @pytest.mark.asyncio
    async def test_get_embedding_alias(self):
        service = GeminiEmbeddingService()

        with patch.object(service, "embed_text", new=AsyncMock(return_value=[0.7, 0.8])) as mock_embed:
            result = await service.get_embedding("test")

        assert result == [0.7, 0.8]
        mock_embed.assert_awaited_once_with("test")

    def test_initialize_no_api_key(self):
        with patch.object(embeddings.settings, "GEMINI_API_KEY", ""), patch.object(
            embeddings.settings, "GOOGLE_API_KEY", ""
        ):
            service = GeminiEmbeddingService()

            with pytest.raises(ValueError):
                service.initialize()


class TestGetEmbeddingServiceFull:
    def test_singleton_creates_new_instance(self):
        embeddings._embedding_service = None

        service = get_embedding_service()

        assert service is not None
        assert isinstance(service, GeminiEmbeddingService)

    def test_singleton_returns_existing(self):
        existing = MagicMock()
        embeddings._embedding_service = existing

        result = get_embedding_service()

        assert result is existing
