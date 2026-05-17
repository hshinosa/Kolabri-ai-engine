"""
RAG Re-Ranking Service with Cross-Encoder
==========================================
Implements cross-encoder based re-ranking for better retrieval quality.

KOL-136: RAG Re-Ranking with Cross-Encoder for Quality Improvement
"""

from typing import List, Dict, Any
import asyncio

from app.core.logging import get_logger
from app.core.config import settings

logger = get_logger(__name__)

try:
    from sentence_transformers import CrossEncoder
    CROSS_ENCODER_AVAILABLE = True
except ImportError:
    CROSS_ENCODER_AVAILABLE = False
    logger.warning("sentence_transformers not installed. Re-ranking disabled.")


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
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        top_k: int = 3,
        retrieve_k: int = 10
    ):
        """
        Initialize Cross-Encoder reranker.
        
        Args:
            model_name: Cross-Encoder model from HuggingFace
            top_k: Number of top results to return after re-ranking
            retrieve_k: Number of results to retrieve for re-ranking
        """
        self.model_name = model_name
        self.top_k = top_k
        self.retrieve_k = retrieve_k
        self.model = None
        self.enabled = settings.ENABLE_RERANKING and CROSS_ENCODER_AVAILABLE
        
        # Caching
        self._cache: Dict[str, List[Dict]] = {}
        self._cache_ttl = 3600  # 1 hour
        self._cache_lock = asyncio.Lock()
        
        # Metrics
        self.total_reranks = 0
        self.cache_hits = 0
        self.avg_rerank_time_ms = 0.0
        
        if self.enabled:
            logger.info(
                "cross_encoder_reranker_initialized",
                model=model_name,
                top_k=top_k,
                retrieve_k=retrieve_k
            )
        else:
            reason = "sentence_transformers_not_installed" if not CROSS_ENCODER_AVAILABLE else "disabled_by_config"
            logger.warning("cross_encoder_reranker_disabled", reason=reason, install_hint="pip install sentence-transformers")
    
    async def load_model(self):
        """Load Cross-Encoder model (lazy loading)."""
        if self.model is None and self.enabled and CROSS_ENCODER_AVAILABLE:
            logger.info("loading_cross_encoder_model")
            self.model = CrossEncoder(self.model_name)
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
            # Generate cache key
            doc_ids = '|'.join([str(doc.get('id', i)) for i, doc in enumerate(documents)])
            cache_key = f"{query}:{doc_ids}:{effective_top_k}"
            
            # Check cache
            async with self._cache_lock:
                if cache_key in self._cache:
                    logger.debug("rerank_cache_hit")
                    self.cache_hits += 1
                    return self._cache[cache_key]
            
            # Lazy load model
            if self.model is None:
                await self.load_model()
            
            import time
            start_time = time.time()
            
            # Prepare pairs for Cross-Encoder
            pairs = [[query, doc.get('content', '')] for doc in documents]
            
            # Get relevance scores
            scores = self.model.predict(pairs)
            
            # Combine documents with scores
            scored_docs = []
            for doc, score in zip(documents, scores):
                doc_copy = doc.copy()
                doc_copy['rerank_score'] = float(score)
                doc_copy['rerank_model'] = self.model_name
                scored_docs.append(doc_copy)
            
            # Sort by score (descending)
            scored_docs.sort(key=lambda x: x['rerank_score'], reverse=True)
            
            # Return top-K
            result = scored_docs[:effective_top_k]
            
            # Cache result
            async with self._cache_lock:
                self._cache[cache_key] = result
            
            # Update metrics
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
                rerank_time_ms=round(rerank_time, 2)
            )
            
            return result
            
        except Exception as e:
            logger.error("reranking_failed", error=str(e))
            # Fallback to original order
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
            'avg_rerank_time_ms': round(self.avg_rerank_time_ms, 2)
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


# Singleton
_reranker: CrossEncoderReranker = None

def get_reranker() -> CrossEncoderReranker:
    """Get CrossEncoderReranker singleton."""
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoderReranker(
            model_name=settings.RERANK_MODEL_NAME,
            top_k=settings.RERANK_TOP_K,
            retrieve_k=settings.RERANK_RETRIEVE_K
        )
    return _reranker
