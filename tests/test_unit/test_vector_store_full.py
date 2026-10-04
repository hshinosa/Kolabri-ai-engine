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
    service._embedding_service.embed_query = AsyncMock(return_value=[0.4, 0.5, 0.6])
    service._embedding_service.dimension = 3
    service._vector_size = 3
    service._initialized = True
    return service


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_collection_reinit_logic():
    service = VectorStoreService()

    async def mock_init_impl():
        service._client = MagicMock()
        service._client.get_collections.return_value = SimpleNamespace(collections=[])
        service._vector_size = 3
        service._initialized = True

    with patch.object(service, "initialize", new=AsyncMock(side_effect=mock_init_impl)) as mock_init, patch(
        "app.services.vector_store.VectorParams", side_effect=lambda **kwargs: kwargs
    ), patch("app.services.vector_store.Distance") as mock_distance:
        mock_distance.COSINE = "cosine"
        await service._ensure_collection("test")

    mock_init.assert_awaited_once_with()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_collection_stats_robust(vector_store_service):
    vector_store_service._client.get_collection.return_value = SimpleNamespace(points_count=10)

    stats = await vector_store_service.get_collection_stats("course1")
    assert stats["document_count"] == 10
    assert stats["collection_name"] == "kolabri_course1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_list_collections_robust(vector_store_service):
    vector_store_service._client.get_collections.return_value = SimpleNamespace(
        collections=[SimpleNamespace(name="kolabri_c1")]
    )
    vector_store_service._client.get_collection.return_value = SimpleNamespace(points_count=5)

    res = await vector_store_service.list_collections()
    assert len(res) == 1
    assert res[0]["name"] == "kolabri_c1"
    assert res[0]["count"] == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_uses_default_collection_name(vector_store_service):
    vector_store_service._client.query_points.return_value = SimpleNamespace(points=[])

    with patch.object(vector_store_service, "_ensure_collection", new=AsyncMock(return_value="default")) as mock_ensure:
        await vector_store_service.search("question")

    mock_ensure.assert_awaited_once_with("default")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delete_collection_initializes_when_needed():
    service = VectorStoreService()
    service._initialized = False

    async def init_side_effect():
        service._initialized = True
        service._client = MagicMock()

    with patch.object(service, "initialize", new=AsyncMock(side_effect=init_side_effect)) as mock_init:
        result = await service.delete_collection("docs")

    mock_init.assert_awaited_once_with()
    assert result is True
