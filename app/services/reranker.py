"""
RAG Re-Ranking Service with Cross-Encoder
==========================================
Implements cross-encoder based re-ranking for better retrieval quality.

KOL-136: RAG Re-Ranking with Cross-Encoder for Quality Improvement

Backend: fastembed.rerank.cross_encoder.TextCrossEncoder (ONNX-runtime).
This avoids the torch dependency, which has no Intel-Mac wheels for Python 3.13.
"""

from typing import List, Dict, Any
import asyncio

from app.core.logging import get_logger
from app.core.config import settings

logger = get_logger(__name__)

try:
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    CROSS_ENCODER_AVAILABLE = True
except ImportError:
    CROSS_ENCODER_AVAILABLE = False
    logger.warning("fastembed not installed. Re-ranking disabled.")


class CrossEncoderReranker:
    """
    Re-ranks retrieved documents using Cross-Encoder for better relevance.

    Cross-Encoders provide better quality than bi-encoders (vector search)
    but are slower. Used for re-ranking top-K results.

    Usage:
        reranker = CrossEncoderReranker()
        reranked_docs = await reranker.rerank(query, retrieved_docs)
    """

    def __init__(
        self,
        model_name: str = "jinaai/jina-reranker-v2-base-multilingual",
        top_k: int = 3,
        retrieve_k: int = 10,
    ):
        """
        Initialize Cross-Encoder reranker.

        Args:
            model_name: Cross-Encoder model from fastembed's supported list
                (e.g. 'jinaai/jina-reranker-v2-base-multilingual',
                'BAAI/bge-reranker-base', 'Xenova/ms-marco-MiniLM-L-6-v2').
            top_k: Number of top results to return after re-ranking
            retrieve_k: Number of results to retrieve for re-ranking
        """
        self.model_name = model_name
        self.top_k = top_k
        self.retrieve_k = retrieve_k
        self.model: TextCrossEncoder | None = None
        self.enabled = settings.ENABLE_RERANKING and CROSS_ENCODER_AVAILABLE

        self._cache: Dict[str, List[Dict]] = {}
        self._cache_ttl = 3600
        self._cache_lock = asyncio.Lock()

        self.total_reranks = 0
        self.cache_hits = 0
        self.avg_rerank_time_ms = 0.0

        if self.enabled:
            logger.info(
                "cross_encoder_reranker_initialized",
                model=model_name,
                top_k=top_k,
                retrieve_k=retrieve_k,
            )
        else:
            reason = "fastembed_not_installed" if not CROSS_ENCODER_AVAILABLE else "disabled_by_config"
            logger.warning(
                "cross_encoder_reranker_disabled",
                reason=reason,
                install_hint="pip install fastembed",
            )

    async def load_model(self):
        """Load Cross-Encoder model (lazy loading)."""
        if self.model is None and self.enabled and CROSS_ENCODER_AVAILABLE:
            logger.info("loading_cross_encoder_model", model=self.model_name)
            cache_dir = settings.RERANK_CACHE_DIR or None
            self.model = TextCrossEncoder(model_name=self.model_name, cache_dir=cache_dir)
            logger.info("cross_encoder_model_loaded")

    async def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Re-rank documents based on query relevance.

        Args:
            query: Search query
            documents: List of retrieved documents with 'content' field

        Returns:
            Re-ranked list of documents (top-k)
        """
        effective_top_k = self.top_k if top_k is None else top_k

        if not self.enabled or not documents:
            return documents[:effective_top_k] if len(documents) > effective_top_k else documents

        try:
            doc_ids = '|'.join([str(doc.get('id', i)) for i, doc in enumerate(documents)])
            cache_key = f"{query}:{doc_ids}:{effective_top_k}"

            async with self._cache_lock:
                if cache_key in self._cache:
                    logger.debug("rerank_cache_hit")
                    self.cache_hits += 1
                    return self._cache[cache_key]

            if self.model is None:
                await self.load_model()

            import time
            start_time = time.time()

            doc_contents = [doc.get('content', '') for doc in documents]
            scores = list(self.model.rerank(query=query, documents=doc_contents))

            scored_docs = []
            for doc, score in zip(documents, scores):
                doc_copy = doc.copy()
                doc_copy['rerank_score'] = float(score)
                doc_copy['rerank_model'] = self.model_name
                scored_docs.append(doc_copy)

            scored_docs.sort(key=lambda x: x['rerank_score'], reverse=True)

            result = scored_docs[:effective_top_k]

            async with self._cache_lock:
                self._cache[cache_key] = result

            rerank_time = (time.time() - start_time) * 1000
            self.total_reranks += 1
            self.avg_rerank_time_ms = (
                (self.avg_rerank_time_ms * (self.total_reranks - 1) + rerank_time) /
                self.total_reranks
            )

            logger.info(
                "reranking_completed",
                original_count=len(documents),
                reranked_count=len(result),
                rerank_time_ms=round(rerank_time, 2),
            )

            return result

        except Exception:
            logger.exception("reranking_failed")
            return documents[:effective_top_k] if len(documents) > effective_top_k else documents

    def get_metrics(self) -> Dict[str, Any]:
        """Get reranker metrics."""
        return {
            'enabled': self.enabled,
            'model_loaded': self.model is not None,
            'model_name': self.model_name,
            'top_k': self.top_k,
            'retrieve_k': self.retrieve_k,
            'total_reranks': self.total_reranks,
            'cache_hits': self.cache_hits,
            'cache_hit_rate': self.cache_hits / self.total_reranks if self.total_reranks > 0 else 0,
            'avg_rerank_time_ms': round(self.avg_rerank_time_ms, 2),
        }

    def disable(self):
        """Disable reranking (fallback mode)."""
        self.enabled = False
        logger.warning("cross_encoder_reranker_disabled")

    def enable(self):
        """Enable reranking."""
        if CROSS_ENCODER_AVAILABLE:
            self.enabled = True
            logger.info("cross_encoder_reranker_enabled")
        else:
            logger.warning("cross_encoder_reranker_cannot_enable_library_missing")


_reranker: CrossEncoderReranker | None = None


def get_reranker() -> CrossEncoderReranker:
    """Get CrossEncoderReranker singleton."""
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoderReranker(
            model_name=settings.RERANK_MODEL_NAME,
            top_k=settings.RERANK_TOP_K,
            retrieve_k=settings.RERANK_RETRIEVE_K,
        )
    return _reranker
