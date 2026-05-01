from typing import List, Optional
from fastembed import TextEmbedding

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class LocalEmbeddingService:
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


_embedding_service: Optional[LocalEmbeddingService] = None


def get_embedding_service() -> LocalEmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = LocalEmbeddingService()
    return _embedding_service
