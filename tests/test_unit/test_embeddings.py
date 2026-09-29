"""Tests for local FastEmbed embedding service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import embeddings
from app.services.embeddings import LocalEmbeddingService, get_embedding_service


def _mock_vector(values):
    vector = MagicMock()
    vector.tolist.return_value = list(values)
    vector.__len__.return_value = len(values)
    return vector


class TestLocalEmbeddingService:
    @pytest.fixture
    def service(self):
        svc = LocalEmbeddingService()
        mock_model = MagicMock()
        mock_model.embed.return_value = iter([_mock_vector([0.1, 0.2, 0.3])])
        mock_model.query_embed.return_value = iter([_mock_vector([0.4, 0.5, 0.6])])
        svc._model = mock_model
        svc._initialized = True
        return svc

    def test_init(self):
        service = LocalEmbeddingService()

        assert service._initialized is False
        assert service._model is None
        assert service._model_name == embeddings.settings.EMBEDDING_MODEL

    def test_initialize(self):
        mock_model = MagicMock()

        with patch("app.services.embeddings.TextEmbedding", return_value=mock_model) as mock_text_embedding:
            service = LocalEmbeddingService()
            service.initialize()

        assert service._initialized is True
        assert service._model is mock_model
        mock_text_embedding.assert_called_once_with(model_name=embeddings.settings.EMBEDDING_MODEL)

    def test_initialize_already_initialized(self, service):
        existing_model = service._model

        with patch("app.services.embeddings.TextEmbedding") as mock_text_embedding:
            service.initialize()

        assert service._model is existing_model
        mock_text_embedding.assert_not_called()

    def test_ensure_initialized_calls_initialize(self):
        service = LocalEmbeddingService()
        service.initialize = MagicMock()

        service._ensure_initialized()

        service.initialize.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_embed_text(self, service):
        result = await service.embed_text("hello")

        assert result == [0.1, 0.2, 0.3]
        service._model.embed.assert_called_once_with(["hello"])

    @pytest.mark.asyncio
    async def test_embed_texts(self, service):
        service._model.embed.return_value = iter(
            [_mock_vector([0.1, 0.2]), _mock_vector([0.3, 0.4])]
        )

        result = await service.embed_texts(["one", "two"])

        assert result == [[0.1, 0.2], [0.3, 0.4]]
        service._model.embed.assert_called_with(["one", "two"])

    @pytest.mark.asyncio
    async def test_embed_query(self, service):
        result = await service.embed_query("what is kolabri?")

        assert result == [0.4, 0.5, 0.6]
        service._model.query_embed.assert_called_once_with("what is kolabri?")

    @pytest.mark.asyncio
    async def test_get_embedding(self, service):
        with patch.object(service, "embed_text", new=AsyncMock(return_value=[0.9, 0.8])) as mock_embed:
            result = await service.get_embedding("alias text")

        assert result == [0.9, 0.8]
        mock_embed.assert_awaited_once_with("alias text")


class TestGetEmbeddingService:
    def test_get_embedding_service_singleton(self):
        embeddings._embedding_service = None

        service1 = get_embedding_service()
        service2 = get_embedding_service()

        assert service1 is service2
        if embeddings.settings.EMBEDDING_PROVIDER == "local":
            assert isinstance(service1, LocalEmbeddingService)
        else:
            assert isinstance(service1, embeddings.VoyageEmbeddingService)

    def test_get_embedding_service_returns_existing_instance(self):
        existing = LocalEmbeddingService()
        embeddings._embedding_service = existing

        result = get_embedding_service()

        assert result is existing
