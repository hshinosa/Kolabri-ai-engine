from typing import List
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

GEMINI_EMBED_URL = "https://generativelanguage.googleapis.com/v1beta/{model}:embedContent"
GEMINI_BATCH_URL = "https://generativelanguage.googleapis.com/v1beta/{model}:batchEmbedContents"


class GeminiEmbeddingService:
    def __init__(self):
        self._initialized = False
        self._api_key: str | None = None
        self._model: str | None = None
        self._client: httpx.AsyncClient | None = None

    def initialize(self) -> None:
        if self._initialized:
            return

        api_key = settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY
        if not api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY is required for embeddings")

        self._api_key = api_key
        self._model = settings.GEMINI_EMBEDDING_MODEL
        self._client = httpx.AsyncClient(timeout=30.0)
        self._initialized = True
        logger.info("gemini_embedding_initialized", model=self._model)

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def embed_text(self, text: str) -> List[float]:
        self._ensure_initialized()

        url = GEMINI_EMBED_URL.format(model=self._model)
        resp = await self._client.post(
            url,
            params={"key": self._api_key},
            json={"model": self._model, "content": {"parts": [{"text": text}]}},
        )
        resp.raise_for_status()
        return resp.json()["embedding"]["values"]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        self._ensure_initialized()

        url = GEMINI_BATCH_URL.format(model=self._model)
        requests = [
            {"model": self._model, "content": {"parts": [{"text": t}]}}
            for t in texts
        ]
        resp = await self._client.post(
            url,
            params={"key": self._api_key},
            json={"requests": requests},
        )
        resp.raise_for_status()
        return [item["values"] for item in resp.json()["embeddings"]]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def embed_query(self, query: str) -> List[float]:
        self._ensure_initialized()

        url = GEMINI_EMBED_URL.format(model=self._model)
        resp = await self._client.post(
            url,
            params={"key": self._api_key},
            json={
                "model": self._model,
                "content": {"parts": [{"text": query}]},
                "taskType": "RETRIEVAL_QUERY",
            },
        )
        resp.raise_for_status()
        return resp.json()["embedding"]["values"]

    async def get_embedding(self, text: str) -> List[float]:
        return await self.embed_text(text)


_embedding_service: GeminiEmbeddingService | None = None


def get_embedding_service() -> GeminiEmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = GeminiEmbeddingService()
    return _embedding_service
