"""Embedding services: Voyage AI (primary) with local FastEmbed fallback.

`get_embedding_service()` returns the provider selected by
`settings.EMBEDDING_PROVIDER` ("voyage" | "local"). The Voyage service
auto-degrades to local FastEmbed when no API key is configured or the
remote API becomes unreachable, so the engine keeps working offline.
"""

import asyncio
from typing import List, Optional

import httpx
from fastembed import TextEmbedding

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_RETRY_STATUS = {429, 500, 502, 503, 504}


class EmbeddingProviderError(RuntimeError):
    """Raised when the primary embedding provider fails permanently."""


class VoyageEmbeddingService:
    """Embeddings via the Voyage AI API. No local model is loaded."""

    def __init__(self) -> None:
        self._initialized = False
        self._model_name: str = settings.VOYAGE_MODEL
        self._dimension: int = settings.VOYAGE_OUTPUT_DIMENSION
        self._batch_size: int = max(1, settings.VOYAGE_BATCH_SIZE)
        self._client: Optional[httpx.AsyncClient] = None
        self._url: str = settings.VOYAGE_BASE_URL.rstrip("/") + "/embeddings"
        self._fallback: Optional["LocalEmbeddingService"] = None

    def initialize(self) -> None:
        if self._initialized:
            return

        if not settings.VOYAGE_API_KEY:
            logger.warning("voyage_api_key_missing_falling_back_to_local")
            self._switch_to_local()
            return

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.VOYAGE_TIMEOUT, connect=10.0),
            headers={
                "Authorization": f"Bearer {settings.VOYAGE_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        self._initialized = True
        logger.info(
            "voyage_embedding_initialized",
            model=self._model_name,
            dimension=self._dimension,
        )

    def _switch_to_local(self) -> None:
        self._fallback = LocalEmbeddingService()
        self._fallback.initialize()
        self._initialized = True

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    @property
    def degraded(self) -> bool:
        """True when the service fell back to the local provider."""
        return self._fallback is not None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._initialized = False

    async def _embed_batch(self, batch: List[str], input_type: str) -> List[List[float]]:
        payload = {
            "input": batch,
            "model": self._model_name,
            "input_type": input_type,
            "output_dimension": self._dimension,
        }
        last_error: Optional[BaseException] = None

        for attempt in range(max(1, settings.VOYAGE_MAX_ATTEMPTS)):
            try:
                response = await self._client.post(self._url, json=payload)
            except httpx.HTTPError as exc:
                last_error = exc
            else:
                if response.status_code == 200:
                    data = response.json().get("data", [])
                    ordered = sorted(data, key=lambda item: item.get("index", 0))
                    return [item["embedding"] for item in ordered]
                last_error = RuntimeError(
                    f"voyage {response.status_code}: {response.text[:200]}"
                )
                if response.status_code not in _RETRY_STATUS:
                    break

            if attempt + 1 < settings.VOYAGE_MAX_ATTEMPTS:
                await asyncio.sleep(settings.VOYAGE_RETRY_BACKOFF * (attempt + 1))

        raise EmbeddingProviderError(f"voyage embedding failed: {last_error}")

    async def _embed(self, texts: List[str], input_type: str) -> List[List[float]]:
        self._ensure_initialized()
        if self.degraded:
            fallback = self._get_fallback()
            if input_type == "query":
                return [await fallback.embed_query(t) for t in texts]
            return await fallback.embed_texts(texts)
        if not texts:
            return []

        embeddings: List[List[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            embeddings.extend(await self._embed_batch(batch, input_type))
        return embeddings

    def _get_fallback(self) -> "LocalEmbeddingService":
        if self._fallback is None:
            self._fallback = LocalEmbeddingService()
            self._fallback.initialize()
        return self._fallback

    async def embed_text(self, text: str) -> List[float]:
        embeddings = await self._embed([text], "document")
        return embeddings[0]

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return await self._embed(texts, "document")

    async def embed_query(self, query: str) -> List[float]:
        embeddings = await self._embed([query], "query")
        return embeddings[0]

    @property
    def degraded(self) -> bool:
        """True when the service permanently fell back to the local provider."""
        return self._fallback is not None and self._client is None

    @property
    def dimension(self) -> int:
        self._ensure_initialized()
        if self.degraded:
            return self._fallback.dimension
        return self._dimension


class LocalEmbeddingService:
    """Backup provider: FastEmbed on-device. Used when Voyage is unavailable."""

    def __init__(self):
        self._initialized = False
        self._model: Optional[TextEmbedding] = None
        self._model_name: str = settings.EMBEDDING_MODEL

    def initialize(self) -> None:
        if self._initialized:
            return

        self._model = TextEmbedding(model_name=self._model_name)
        self._initialized = True
        logger.info("local_embedding_initialized", model=self._model_name)

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    async def embed_text(self, text: str) -> List[float]:
        self._ensure_initialized()
        embeddings = list(self._model.embed([text]))
        return embeddings[0].tolist()

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        self._ensure_initialized()
        embeddings = list(self._model.embed(texts))
        return [e.tolist() for e in embeddings]

    async def embed_query(self, query: str) -> List[float]:
        self._ensure_initialized()
        embeddings = list(self._model.query_embed(query))
        return embeddings[0].tolist()

    async def get_embedding(self, text: str) -> List[float]:
        return await self.embed_text(text)

    @property
    def dimension(self) -> int:
        self._ensure_initialized()
        test = list(self._model.embed(["test"]))
        return len(test[0])


_embedding_service = None


def get_embedding_service():
    """Return the embedding provider selected by EMBEDDING_PROVIDER."""
    global _embedding_service
    if _embedding_service is None:
        if settings.EMBEDDING_PROVIDER == "local":
            _embedding_service = LocalEmbeddingService()
            logger.info("embedding_provider_selected", provider="local")
        else:
            _embedding_service = VoyageEmbeddingService()
            logger.info(
                "embedding_provider_selected",
                provider="local" if settings.EMBEDDING_PROVIDER != "voyage" else "voyage",
            )
    return _embedding_service
