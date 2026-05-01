"""Comprehensive tests for Qdrant-backed vector store service."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import vector_store
from app.services.vector_store import VectorStoreService, get_vector_store


def _point(content, payload=None, score=0.9):
    return SimpleNamespace(payload={"content": content, **(payload or {})}, score=score)


class TestVectorStoreService:
    @pytest.fixture
    def vector_store_service(self):
        svc = VectorStoreService()
        svc._client = MagicMock()
        svc._async_client = MagicMock()
        svc._embedding_service = MagicMock()
        svc._embedding_service.embed_texts = AsyncMock(return_value=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
        svc._embedding_service.embed_query = AsyncMock(return_value=[0.9, 0.8, 0.7])
        svc._embedding_service.dimension = 3
        svc._vector_size = 3
        svc._initialized = True
        return svc

    @pytest.mark.asyncio
    async def test_get_or_create_collection(self, vector_store_service):
        with patch.object(vector_store_service, "_ensure_collection", new=AsyncMock(return_value="kolabri_course123")) as mock_ensure:
            result = await vector_store_service.get_or_create_collection("course123")

        assert result == "kolabri_course123"
        mock_ensure.assert_awaited_once_with("kolabri_course123")

    @pytest.mark.asyncio
    async def test_add_documents_with_collection_name(self, vector_store_service):
        with patch.object(vector_store_service, "_ensure_collection", new=AsyncMock(return_value="docs")) as mock_ensure, patch(
            "app.services.vector_store.uuid.uuid5", side_effect=["uuid-1", "uuid-2"]
        ) as mock_uuid, patch(
            "app.services.vector_store.PointStruct", side_effect=lambda **kwargs: kwargs
        ) as mock_point_struct:
            await vector_store_service.add_documents(
                documents=["doc1", "doc2"],
                metadatas=[{"page": 1}, {"page": 2}],
                ids=["id1", "id2"],
                collection_name="docs",
            )

        mock_ensure.assert_awaited_once_with("docs")
        vector_store_service._embedding_service.embed_texts.assert_awaited_once_with(["doc1", "doc2"])
        assert mock_point_struct.call_count == 2
        assert mock_uuid.call_count == 2
        upsert_kwargs = vector_store_service._client.upsert.call_args.kwargs
        assert upsert_kwargs["collection_name"] == "docs"
        assert upsert_kwargs["points"][0]["payload"] == {
            "page": 1,
            "content": "doc1",
            "document_id": "id1",
        }
        assert upsert_kwargs["points"][1]["vector"] == [0.4, 0.5, 0.6]

    @pytest.mark.asyncio
    async def test_add_documents_with_course_id(self, vector_store_service):
        with patch.object(vector_store_service, "_ensure_collection", new=AsyncMock(return_value="kolabri_course1")) as mock_ensure, patch(
            "app.services.vector_store.uuid.uuid5", return_value="uuid-1"
        ), patch("app.services.vector_store.PointStruct", side_effect=lambda **kwargs: kwargs):
            await vector_store_service.add_documents(
                documents=["doc1"],
                metadatas=[{"source": "pdf"}],
                ids=["id1"],
                course_id="course1",
            )

        mock_ensure.assert_awaited_once_with("kolabri_course1")

    @pytest.mark.asyncio
    async def test_search_formats_qdrant_results(self, vector_store_service):
        vector_store_service._client.query_points.return_value = SimpleNamespace(
            points=[
                _point("First", {"page": 1, "source": "a.pdf"}, 0.91),
                _point("Second", {"page": 2}, 0.77),
            ]
        )

        with patch.object(vector_store_service, "_ensure_collection", new=AsyncMock(return_value="docs")) as mock_ensure:
            results = await vector_store_service.search(
                query="hello",
                collection_name="docs",
                n_results=2,
            )

        mock_ensure.assert_awaited_once_with("docs")
        vector_store_service._embedding_service.embed_query.assert_awaited_once_with("hello")
        assert results == [
            {"content": "First", "metadata": {"page": 1, "source": "a.pdf"}, "score": 0.91},
            {"content": "Second", "metadata": {"page": 2}, "score": 0.77},
        ]

    @pytest.mark.asyncio
    async def test_search_builds_filter_from_where(self, vector_store_service):
        vector_store_service._client.query_points.return_value = SimpleNamespace(points=[])

        with patch.object(vector_store_service, "_ensure_collection", new=AsyncMock(return_value="docs")), patch(
            "app.services.vector_store.MatchValue", side_effect=lambda **kwargs: {"match": kwargs}
        ) as mock_match_value, patch(
            "app.services.vector_store.FieldCondition", side_effect=lambda **kwargs: {"condition": kwargs}
        ) as mock_field_condition, patch(
            "app.services.vector_store.Filter", side_effect=lambda **kwargs: {"filter": kwargs}
        ) as mock_filter:
            await vector_store_service.search(
                query="hello",
                collection_name="docs",
                n_results=3,
                where={"course_id": "c1", "page": 2},
            )

        assert mock_match_value.call_count == 2
        assert mock_field_condition.call_count == 2
        mock_filter.assert_called_once()
        query_kwargs = vector_store_service._client.query_points.call_args.kwargs
        assert query_kwargs["query_filter"] == {
            "filter": {
                "must": [
                    {"condition": {"key": "course_id", "match": {"match": {"value": "c1"}}}},
                    {"condition": {"key": "page", "match": {"match": {"value": 2}}}},
                ]
            }
        }

    @pytest.mark.asyncio
    async def test_search_returns_empty_when_collection_lookup_fails(self, vector_store_service):
        with patch.object(vector_store_service, "_ensure_collection", new=AsyncMock(side_effect=Exception("missing"))):
            result = await vector_store_service.search("hello")

        assert result == []
        vector_store_service._embedding_service.embed_query.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_query_returns_legacy_format_with_default_top_k(self, vector_store_service):
        with patch.object(vector_store_service, "search", new=AsyncMock(return_value=[
            {"content": "Doc A", "metadata": {"page": 1}, "score": 0.9},
            {"content": "Doc B", "metadata": {"page": 2}, "score": 0.6},
        ])) as mock_search, patch("app.services.vector_store.settings.TOP_K_RESULTS", 7):
            result = await vector_store_service.query(course_id="course1", query_text="what?")

        mock_search.assert_awaited_once_with(
            query="what?",
            collection_name="kolabri_course1",
            n_results=7,
        )
        assert result == {
            "documents": [["Doc A", "Doc B"]],
            "metadatas": [[{"page": 1}, {"page": 2}]],
            "distances": [[0.09999999999999998, 0.4]],
        }

    @pytest.mark.asyncio
    async def test_query_respects_custom_n_results(self, vector_store_service):
        with patch.object(vector_store_service, "search", new=AsyncMock(return_value=[])) as mock_search:
            await vector_store_service.query(course_id="course1", query_text="what?", n_results=2)

        mock_search.assert_awaited_once_with(
            query="what?",
            collection_name="kolabri_course1",
            n_results=2,
        )

    @pytest.mark.asyncio
    async def test_delete_documents_by_ids(self, vector_store_service):
        with patch.object(vector_store_service, "_ensure_collection", new=AsyncMock(return_value="docs")), patch(
            "app.services.vector_store.uuid.uuid5", side_effect=["uuid-1", "uuid-2"]
        ), patch("app.services.vector_store.models.PointIdsList", side_effect=lambda **kwargs: kwargs) as mock_ids_list:
            await vector_store_service.delete_documents(ids=["id1", "id2"], collection_name="docs")

        mock_ids_list.assert_called_once_with(points=["uuid-1", "uuid-2"])
        vector_store_service._client.delete.assert_called_once_with(
            collection_name="docs",
            points_selector={"points": ["uuid-1", "uuid-2"]},
        )

    @pytest.mark.asyncio
    async def test_delete_documents_by_where(self, vector_store_service):
        with patch.object(vector_store_service, "_ensure_collection", new=AsyncMock(return_value="docs")), patch(
            "app.services.vector_store.MatchValue", side_effect=lambda **kwargs: {"match": kwargs}
        ), patch(
            "app.services.vector_store.FieldCondition", side_effect=lambda **kwargs: {"condition": kwargs}
        ), patch(
            "app.services.vector_store.Filter", side_effect=lambda **kwargs: {"filter": kwargs}
        ), patch(
            "app.services.vector_store.models.FilterSelector", side_effect=lambda **kwargs: kwargs
        ) as mock_filter_selector:
            await vector_store_service.delete_documents(where={"course_id": "c1"}, collection_name="docs")

        mock_filter_selector.assert_called_once_with(
            filter={
                "filter": {
                    "must": [
                        {"condition": {"key": "course_id", "match": {"match": {"value": "c1"}}}}
                    ]
                }
            }
        )

    @pytest.mark.asyncio
    async def test_delete_documents_raises_on_error(self, vector_store_service):
        with patch.object(vector_store_service, "_ensure_collection", new=AsyncMock(side_effect=RuntimeError("boom"))):
            with pytest.raises(RuntimeError, match="boom"):
                await vector_store_service.delete_documents(ids=["id1"])

    @pytest.mark.asyncio
    async def test_delete_collection_success(self, vector_store_service):
        result = await vector_store_service.delete_collection("docs")

        assert result is True
        vector_store_service._client.delete_collection.assert_called_once_with(collection_name="docs")

    @pytest.mark.asyncio
    async def test_delete_collection_failure(self, vector_store_service):
        vector_store_service._client.delete_collection.side_effect = Exception("missing")

        result = await vector_store_service.delete_collection("docs")

        assert result is False

    @pytest.mark.asyncio
    async def test_list_collections(self, vector_store_service):
        vector_store_service._client.get_collections.return_value = SimpleNamespace(
            collections=[SimpleNamespace(name="c1"), SimpleNamespace(name="c2")]
        )
        vector_store_service._client.get_collection.side_effect = [
            SimpleNamespace(points_count=5),
            SimpleNamespace(points_count=9),
        ]

        result = await vector_store_service.list_collections()

        assert result == [
            {"name": "c1", "metadata": {}, "count": 5},
            {"name": "c2", "metadata": {}, "count": 9},
        ]

    @pytest.mark.asyncio
    async def test_get_collection_stats(self, vector_store_service):
        vector_store_service._client.get_collection.return_value = SimpleNamespace(points_count=25)

        with patch.object(vector_store_service, "_ensure_collection", new=AsyncMock(return_value="kolabri_course1")) as mock_ensure:
            result = await vector_store_service.get_collection_stats("course1")

        mock_ensure.assert_awaited_once_with("kolabri_course1")
        assert result == {
            "course_id": "course1",
            "collection_name": "kolabri_course1",
            "document_count": 25,
        }


class TestGetVectorStore:
    def test_get_vector_store_singleton(self):
        vector_store._vector_store = None

        store1 = get_vector_store()
        store2 = get_vector_store()

        assert store1 is store2
        assert isinstance(store1, VectorStoreService)

    def test_get_vector_store_returns_existing_instance(self):
        existing = VectorStoreService()
        vector_store._vector_store = existing

        result = get_vector_store()

        assert result is existing
