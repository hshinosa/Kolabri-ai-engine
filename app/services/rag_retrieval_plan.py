from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from app.services.rag_quality import RetrievalQualityControls

QueryType = Literal["factual", "conceptual", "procedural"]


@dataclass(frozen=True)
class RetrievalPlan:
    top_k: int
    score_threshold: float
    use_reranker: bool
    rerank_top_n: int
    grounding_threshold: float


def build_retrieval_plan(
    query: str,
    query_type: Optional[QueryType],
    quality_controls: RetrievalQualityControls,
    requested_n_results: Optional[int] = None,
    requested_score_threshold: Optional[float] = None,
) -> RetrievalPlan:
    search_plan = quality_controls.resolve_search_plan(
        requested_n_results=requested_n_results,
        score_threshold=requested_score_threshold,
    )

    score_threshold = search_plan.score_threshold
    rerank_top_n = quality_controls.rerank_top_k

    if query_type == "factual":
        score_threshold = max(score_threshold, quality_controls.similarity_threshold)
        rerank_top_n = max(1, min(rerank_top_n, 3))
    elif query_type == "conceptual":
        score_threshold = max(0.0, score_threshold - 0.05)
    elif query_type == "procedural":
        rerank_top_n = max(1, min(rerank_top_n, 3))

    return RetrievalPlan(
        top_k=search_plan.search_n_results,
        score_threshold=score_threshold,
        use_reranker=search_plan.reranking_enabled,
        rerank_top_n=rerank_top_n,
        grounding_threshold=quality_controls.grounding_threshold,
    )
