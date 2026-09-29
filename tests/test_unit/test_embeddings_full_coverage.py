"""Additional coverage tests for local FastEmbed embedding service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import embeddings
from app.services.embeddings import LocalEmbeddingService, get_embedding_service


def _mock_vector(values):
    vector = MagicMock()
    vector.tolist.return_value = list(values)
    vector.__len__.return_value = len(values)
    return vector


class TestLocalEmbeddingServiceFull:
    def test_initialize_already_initialized(self):
        service = LocalEmbeddingService()
        existing_model = MagicMock()
        service._initialized = True
        service._model = existing_model

        with patch("app.services.embeddings.TextEmbedding") as mock_text_embedding:
            service.initialize()

        assert service._model is existing_model
        mock_text_embedding.assert_not_called()

    @pytest.mark.asyncio
    async def test_embed_text_auto_init(self):
        service = LocalEmbeddingService()
        mock_model = MagicMock()
        mock_model.embed.return_value = iter([_mock_vector([0.1, 0.2])])

        with patch("app.services.embeddings.TextEmbedding", return_value=mock_model):
            result = await service.embed_text("test")

        assert result == [0.1, 0.2]
        assert service._initialized is True
        assert service._model is mock_model

    @pytest.mark.asyncio
    async def test_embed_texts_auto_init(self):
        service = LocalEmbeddingService()
        mock_model = MagicMock()
        mock_model.embed.return_value = iter([_mock_vector([0.1, 0.2])])

        with patch("app.services.embeddings.TextEmbedding", return_value=mock_model):
            result = await service.embed_texts(["test"])

        assert result == [[0.1, 0.2]]

    @pytest.mark.asyncio
    async def test_embed_query_auto_init(self):
        service = LocalEmbeddingService()
        mock_model = MagicMock()
        mock_model.embed.return_value = iter([_mock_vector([0.9, 0.8])])
        mock_model.query_embed.return_value = iter([_mock_vector([0.5, 0.6])])

        with patch("app.services.embeddings.TextEmbedding", return_value=mock_model):
            result = await service.embed_query("query")

        assert result == [0.5, 0.6]

    @pytest.mark.asyncio
    async def test_get_embedding_alias(self):
        service = LocalEmbeddingService()

        with patch.object(service, "embed_text", new=AsyncMock(return_value=[0.7, 0.8])) as mock_embed:
            result = await service.get_embedding("test")

        assert result == [0.7, 0.8]
        mock_embed.assert_awaited_once_with("test")

    def test_dimension_auto_init(self):
        service = LocalEmbeddingService()
        mock_model = MagicMock()
        mock_model.embed.return_value = iter([_mock_vector([1.0, 2.0, 3.0])])

        with patch("app.services.embeddings.TextEmbedding", return_value=mock_model):
            result = service.dimension

        assert result == 3
        assert service._initialized is True

    @pytest.mark.asyncio
    async def test_embed_text_returns_first_embedding_only(self):
        service = LocalEmbeddingService()
        mock_model = MagicMock()
        mock_model.embed.return_value = iter(
            [_mock_vector([0.1, 0.2]), _mock_vector([9.9, 9.8])]
        )
        service._model = mock_model
        service._initialized = True

        result = await service.embed_text("one")

        assert result == [0.1, 0.2]


class TestGetEmbeddingServiceFull:
    def test_singleton_creates_new_instance(self):
        embeddings._embedding_service = None

        service = get_embedding_service()

        assert service is not None
        if embeddings.settings.EMBEDDING_PROVIDER == "local":
            assert isinstance(service, LocalEmbeddingService)
        else:
            assert isinstance(service, embeddings.VoyageEmbeddingService)

    def test_singleton_returns_existing(self):
        existing = MagicMock()
        embeddings._embedding_service = existing

        result = get_embedding_service()

        assert result is existing
