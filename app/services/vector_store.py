import asyncio
import uuid
from typing import List, Dict, Any, Optional

from qdrant_client import QdrantClient, AsyncQdrantClient, models
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    Range,
)

from app.core.config import settings
from app.core.logging import get_logger
from app.services.embeddings import get_embedding_service

logger = get_logger(__name__)


class VectorStoreService:
    def __init__(self):
        self._client: Optional[QdrantClient] = None
        self._async_client: Optional[AsyncQdrantClient] = None
        self._initialized = False
        self._embedding_service = None
        self._vector_size: Optional[int] = None

    async def initialize(self) -> None:
        if self._initialized:
            return

        self._embedding_service = get_embedding_service()
        self._embedding_service.initialize()
        self._vector_size = self._embedding_service.dimension

        self._client = QdrantClient(
            url=settings.QDRANT_URL,
            timeout=30,
        )
        self._async_client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            timeout=30,
        )

        self._initialized = True
        logger.info(
            "vector_store_initialized",
            url=settings.QDRANT_URL,
            vector_size=self._vector_size,
        )

    async def _ensure_collection(self, collection_name: str) -> str:
        if not self._initialized:
            await self.initialize()

        collections = self._client.get_collections().collections
        existing_names = [c.name for c in collections]

        if collection_name not in existing_names:
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=self._vector_size,
                    distance=Distance.COSINE,
                ),
            )
            self._client.create_payload_index(
                collection_name=collection_name,
                field_name="document_id",
                field_schema="keyword",
            )
            logger.info("collection_created", collection=collection_name)

        return collection_name

    def _get_collection_name(self, course_id: str) -> str:
        return f"{settings.QDRANT_COLLECTION_PREFIX}_{course_id}"

    async def get_or_create_collection(self, course_id: str) -> str:
        collection_name = self._get_collection_name(course_id)
        return await self._ensure_collection(collection_name)

    async def add_documents(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        ids: List[str],
        collection_name: Optional[str] = None,
        course_id: Optional[str] = None,
    ) -> None:
        target_collection = collection_name or (
            self._get_collection_name(course_id) if course_id else "default"
        )

        # Fail loudly before any side effect: misaligned inputs would attach
        # wrong metadata/ids to documents (silent data corruption in Qdrant).
        if len(documents) != len(metadatas) or len(documents) != len(ids):
            logger.error(
                "add_documents_length_mismatch",
                collection=target_collection,
                documents=len(documents),
                metadatas=len(metadatas),
                ids=len(ids),
            )
            raise ValueError(
                "documents, metadatas, and ids must have equal lengths: "
                f"documents={len(documents)}, metadatas={len(metadatas)}, "
                f"ids={len(ids)}"
            )

        await self._ensure_collection(target_collection)

        embeddings = await self._embedding_service.embed_texts(documents)

        # Embeddings come from an external provider that is not validated to
        # return exactly len(documents) items. Fewer embeddings would silently
        # drop documents from the upsert; raise instead of corrupting.
        if len(embeddings) < len(documents):
            logger.error(
                "add_documents_embedding_length_mismatch",
                collection=target_collection,
                documents=len(documents),
                embeddings=len(embeddings),
            )
            raise ValueError(
                "embedding provider returned fewer embeddings than documents: "
                f"documents={len(documents)}, embeddings={len(embeddings)}"
            )
        if len(embeddings) > len(documents):
            # Extra trailing embeddings cannot pair with any document; every
            # document still gets its own embedding. Trim explicitly so the
            # zip below is provably length-equal.
            logger.warning(
                "add_documents_extra_embeddings",
                collection=target_collection,
                documents=len(documents),
                embeddings=len(embeddings),
            )
            embeddings = embeddings[: len(documents)]

        points = []
        for doc, meta, doc_id, embedding in zip(
            documents, metadatas, ids, embeddings, strict=True
        ):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, doc_id))
            # Keep the caller's document_id (the knowledge-base id) intact: it is the
            # field deletion filters on. The per-chunk identifier lives in chunk_id.
            payload = {**meta, "content": doc, "chunk_id": doc_id}
            payload.setdefault("document_id", doc_id)
            points.append(PointStruct(id=point_id, vector=embedding, payload=payload))

        self._client.upsert(
            collection_name=target_collection,
            points=points,
        )

        logger.info(
            "documents_added", collection=target_collection, count=len(documents)
        )

    async def search(
        self,
        query: str,
        collection_name: Optional[str] = None,
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        target_collection = collection_name or "default"

        try:
            await self._ensure_collection(target_collection)
        except Exception:
            logger.exception("collection_not_found", collection=target_collection)
            return []

        query_embedding = await self._embedding_service.embed_query(query)
        effective_score_threshold = (
            settings.SIMILARITY_THRESHOLD
            if score_threshold is None
            else score_threshold
        )

        query_filter = None
        if where:
            conditions = []
            for key, value in where.items():
                if isinstance(value, dict) and "$lte" in value:
                    conditions.append(
                        FieldCondition(key=key, range=Range(lte=float(value["$lte"])))
                    )
                else:
                    conditions.append(
                        FieldCondition(key=key, match=MatchValue(value=value))
                    )
            query_filter = Filter(must=conditions)

        # PERF-AI-10: Wrap blocking Qdrant query_points in asyncio.to_thread
        results = await asyncio.to_thread(
            self._client.query_points,
            collection_name=target_collection,
            query=query_embedding,
            limit=n_results,
            query_filter=query_filter,
            with_payload=True,
        )

        formatted = []
        for point in results.points:
            if point.score < effective_score_threshold:
                continue
            payload = point.payload or {}
            content = payload.pop("content", "")
            formatted.append(
                {
                    "content": content,
                    "metadata": payload,
                    "score": point.score,
                }
            )

        logger.debug(
            "search_executed",
            collection=target_collection,
            results_count=len(formatted),
        )
        return formatted

    async def query(
        self,
        course_id: str,
        query_text: str,
        n_results: int = None,
        score_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        if n_results is None:
            n_results = settings.TOP_K_RESULTS

        collection_name = self._get_collection_name(course_id)
        results = await self.search(
            query=query_text,
            collection_name=collection_name,
            n_results=n_results,
            score_threshold=score_threshold,
        )

        documents = [[r["content"] for r in results]]
        metadatas = [[r["metadata"] for r in results]]
        distances = [[1 - r["score"] for r in results]]

        return {
            "documents": documents,
            "metadatas": metadatas,
            "distances": distances,
        }

    async def delete_documents(
        self,
        ids: Optional[List[str]] = None,
        collection_name: Optional[str] = None,
        where: Optional[Dict[str, Any]] = None,
    ) -> None:
        target_collection = collection_name or "default"

        try:
            await self._ensure_collection(target_collection)

            if ids:
                # Points are keyed by uuid5(chunk_id) where chunk_id is
                # f"{document_id}_p{page}_c{index}" (see document_processing/chunking.py),
                # so uuid5(document_id) never matches a stored point. Delete by the
                # document_id payload field instead, which every chunk carries.
                for doc_id in ids:
                    self._client.delete(
                        collection_name=target_collection,
                        points_selector=models.FilterSelector(
                            filter=Filter(
                                must=[
                                    FieldCondition(
                                        key="document_id",
                                        match=MatchValue(value=doc_id),
                                    )
                                ]
                            )
                        ),
                    )
            elif where:
                conditions = []
                for key, value in where.items():
                    conditions.append(
                        FieldCondition(key=key, match=MatchValue(value=value))
                    )
                self._client.delete(
                    collection_name=target_collection,
                    points_selector=models.FilterSelector(
                        filter=Filter(must=conditions)
                    ),
                )

            logger.info(
                "documents_deleted",
                collection=target_collection,
                ids_count=len(ids) if ids else 0,
            )
        except Exception:
            logger.exception("delete_failed", collection=target_collection)
            raise

    async def delete_collection(self, collection_name: str) -> bool:
        if not self._initialized:
            await self.initialize()

        try:
            self._client.delete_collection(collection_name=collection_name)
            logger.info("collection_deleted", collection=collection_name)
            return True
        except Exception:
            logger.exception("collection_delete_failed", collection=collection_name)
            return False

    async def list_collections(self) -> List[Dict[str, Any]]:
        if not self._initialized:
            await self.initialize()

        collections = self._client.get_collections().collections

        result = []
        for col in collections:
            info = self._client.get_collection(col.name)
            result.append(
                {
                    "name": col.name,
                    "metadata": {},
                    "count": info.points_count,
                }
            )

        return result

    async def get_collection_stats(self, course_id: str) -> Dict[str, Any]:
        collection_name = self._get_collection_name(course_id)
        await self._ensure_collection(collection_name)

        info = self._client.get_collection(collection_name)

        return {
            "course_id": course_id,
            "collection_name": collection_name,
            "document_count": info.points_count,
        }


_vector_store: Optional[VectorStoreService] = None


def get_vector_store() -> VectorStoreService:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStoreService()
    return _vector_store
