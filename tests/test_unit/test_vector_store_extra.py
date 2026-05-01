from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.vector_store import VectorStoreService


@pytest.fixture
def vector_store_service():
    service = VectorStoreService()
    service._client = MagicMock()
    service._async_client = MagicMock()
    service._embedding_service = MagicMock()
    service._embedding_service.embed_texts = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
    service._embedding_service.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])
    service._embedding_service.dimension = 3
    service._vector_size = 3
    service._initialized = True
    return service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_legacy_full(vector_store_service):
    with patch.object(vector_store_service, "search", new=AsyncMock(return_value=[
        {"content": "Chunk", "metadata": {"page": 1}, "score": 0.8}
    ])):
        res = await vector_store_service.query("c1", "q1", n_results=1)

    assert res == {
        "documents": [["Chunk"]],
        "metadatas": [[{"page": 1}]],
        "distances": [[0.19999999999999996]],
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_documents_with_where(vector_store_service):
    with patch.object(vector_store_service, "_ensure_collection", new=AsyncMock(return_value="test")), patch(
        "app.services.vector_store.MatchValue", side_effect=lambda **kwargs: {"match": kwargs}
    ), patch(
        "app.services.vector_store.FieldCondition", side_effect=lambda **kwargs: {"condition": kwargs}
    ), patch(
        "app.services.vector_store.Filter", side_effect=lambda **kwargs: {"filter": kwargs}
    ), patch(
        "app.services.vector_store.models.FilterSelector", side_effect=lambda **kwargs: kwargs
    ):
        await vector_store_service.delete_documents(where={"source": 1}, collection_name="test")

    vector_store_service._client.delete.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_collection_not_found(vector_store_service):
    vector_store_service._client.delete_collection.side_effect = Exception("Not found")

    res = await vector_store_service.delete_collection("nonexistent")
    assert res is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initialize_twice():
    service = VectorStoreService()
    embedding_service = MagicMock()
    embedding_service.initialize = MagicMock()
    type(embedding_service).dimension = property(lambda self: 3)

    with patch("app.services.vector_store.get_embedding_service", return_value=embedding_service), patch(
        "app.services.vector_store.QdrantClient", return_value=MagicMock()
    ), patch("app.services.vector_store.AsyncQdrantClient", return_value=MagicMock()):
        await service.initialize()
        assert service._initialized is True
        first_client = service._client
        await service.initialize()

    assert service._client is first_client


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_collections_initializes_when_needed():
    service = VectorStoreService()
    service._initialized = False

    async def init_side_effect():
        service._initialized = True
        service._client = MagicMock()
        service._client.get_collections.return_value = SimpleNamespace(collections=[SimpleNamespace(name="docs")])
        service._client.get_collection.return_value = SimpleNamespace(points_count=4)

    with patch.object(service, "initialize", new=AsyncMock(side_effect=init_side_effect)) as mock_init:
        result = await service.list_collections()

    mock_init.assert_awaited_once_with()
    assert result == [{"name": "docs", "metadata": {}, "count": 4}]
