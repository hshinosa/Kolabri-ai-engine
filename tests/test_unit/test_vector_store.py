from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.vector_store import VectorStoreService


class TestVectorStoreService:
    @pytest.fixture
    def service(self):
        svc = VectorStoreService()
        svc._client = MagicMock()
        svc._async_client = MagicMock()
        svc._embedding_service = MagicMock()
        svc._embedding_service.embed_texts = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
        svc._embedding_service.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
        svc._embedding_service.dimension = 3
        svc._vector_size = 3
        svc._initialized = True
        return svc

    def test_init(self):
        svc = VectorStoreService()

        assert svc._client is None
        assert svc._async_client is None
        assert svc._embedding_service is None
        assert svc._vector_size is None
        assert svc._initialized is False

    @pytest.mark.asyncio
    async def test_initialize(self):
        mock_embedding_service = MagicMock()
        mock_embedding_service.initialize = MagicMock()
        type(mock_embedding_service).dimension = property(lambda self: 6)
        mock_client = MagicMock()
        mock_async_client = MagicMock()

        with patch("app.services.vector_store.get_embedding_service", return_value=mock_embedding_service) as mock_get_service, patch(
            "app.services.vector_store.QdrantClient", return_value=mock_client
        ) as mock_qdrant_client, patch(
            "app.services.vector_store.AsyncQdrantClient", return_value=mock_async_client
        ) as mock_async_qdrant_client:
            svc = VectorStoreService()
            await svc.initialize()

        assert svc._initialized is True
        assert svc._embedding_service is mock_embedding_service
        assert svc._client is mock_client
        assert svc._async_client is mock_async_client
        assert svc._vector_size == 6
        mock_get_service.assert_called_once_with()
        mock_embedding_service.initialize.assert_called_once_with()
        mock_qdrant_client.assert_called_once()
        mock_async_qdrant_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_already_initialized(self, service):
        existing_client = service._client

        with patch("app.services.vector_store.get_embedding_service") as mock_get_service:
            await service.initialize()

        assert service._client is existing_client
        mock_get_service.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_collection_creates_missing_collection(self, service):
        service._client.get_collections.return_value = SimpleNamespace(collections=[])

        with patch("app.services.vector_store.VectorParams", side_effect=lambda **kwargs: kwargs) as mock_vector_params, patch(
            "app.services.vector_store.Distance"
        ) as mock_distance:
            mock_distance.COSINE = "cosine"
            result = await service._ensure_collection("course_docs")

        assert result == "course_docs"
        mock_vector_params.assert_called_once_with(size=3, distance="cosine")
        service._client.create_collection.assert_called_once_with(
            collection_name="course_docs",
            vectors_config={"size": 3, "distance": "cosine"},
        )
        service._client.create_payload_index.assert_called_once_with(
            collection_name="course_docs",
            field_name="document_id",
            field_schema="keyword",
        )

    @pytest.mark.asyncio
    async def test_ensure_collection_skips_existing_collection(self, service):
        service._client.get_collections.return_value = SimpleNamespace(
            collections=[SimpleNamespace(name="course_docs")]
        )

        result = await service._ensure_collection("course_docs")

        assert result == "course_docs"
        service._client.create_collection.assert_not_called()
        service._client.create_payload_index.assert_not_called()

    def test_get_collection_name(self):
        svc = VectorStoreService()

        with patch("app.services.vector_store.settings.QDRANT_COLLECTION_PREFIX", "kolabri"):
            result = svc._get_collection_name("course123")

        assert result == "kolabri_course123"
