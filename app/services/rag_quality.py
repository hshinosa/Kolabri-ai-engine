from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.config import settings


@dataclass(frozen=True)
class RetrievalSearchPlan:
    search_n_results: int
    output_n_results: int
    score_threshold: float
    reranking_enabled: bool


@dataclass(frozen=True)
class RetrievalQualityControls:
    top_k_results: int
    similarity_threshold: float
    semantic_cache_threshold: float
    reranking_enabled: bool
    rerank_top_k: int
    rerank_retrieve_k: int
    grounding_threshold: float

    @classmethod
    def from_settings(cls) -> "RetrievalQualityControls":
        return cls(
            top_k_results=settings.TOP_K_RESULTS,
            similarity_threshold=settings.SIMILARITY_THRESHOLD,
            semantic_cache_threshold=settings.RAG_SEMANTIC_CACHE_THRESHOLD,
            reranking_enabled=settings.ENABLE_RERANKING,
            rerank_top_k=settings.RERANK_TOP_K,
            rerank_retrieve_k=settings.RERANK_RETRIEVE_K,
            grounding_threshold=settings.RAG_GROUNDING_THRESHOLD,
        )

    def resolve_search_plan(
        self,
        requested_n_results: Optional[int] = None,
        score_threshold: Optional[float] = None,
    ) -> RetrievalSearchPlan:
        output_n_results = requested_n_results or self.top_k_results
        effective_score_threshold = (
            self.similarity_threshold if score_threshold is None else score_threshold
        )
        search_n_results = output_n_results

        if self.reranking_enabled:
            search_n_results = max(output_n_results, self.rerank_retrieve_k)

        return RetrievalSearchPlan(
            search_n_results=search_n_results,
            output_n_results=output_n_results,
            score_threshold=effective_score_threshold,
            reranking_enabled=self.reranking_enabled,
        )


@dataclass(frozen=True)
class RetrievalEvaluationCase:
    query: str
    expected_sources: list[str]
    retrieved_sources: list[str]
    fallback_used: bool = False


@dataclass(frozen=True)
class RetrievalQualityReviewCriteria:
    min_cases: int = 1
    min_pass_rate: float = 0.0
    min_source_recall: float = 0.0
    min_top_hit_rate: float = 0.0
    require_fallback_coverage: bool = False

    @classmethod
    def internal_defaults(cls) -> "RetrievalQualityReviewCriteria":
        return cls(
            min_cases=3,
            min_pass_rate=0.66,
            min_source_recall=0.5,
            min_top_hit_rate=0.33,
            require_fallback_coverage=True,
        )


@dataclass(frozen=True)
class RetrievalQualitySummary:
    total_cases: int
    passed_cases: int
    fallback_cases: int
    pass_rate: float
    average_source_recall: float
    top_hit_rate: float
    passed: bool


@dataclass(frozen=True)
class InternalRetrievalQualityWorkflow:
    controls: RetrievalQualityControls
    criteria: RetrievalQualityReviewCriteria
    deferred_surfaces: tuple[str, ...] = (
        "public_api_request_parameters",
        "admin_ops_runtime_endpoints",
    )

    @classmethod
    def from_settings(cls) -> "InternalRetrievalQualityWorkflow":
        return cls(
            controls=RetrievalQualityControls.from_settings(),
            criteria=RetrievalQualityReviewCriteria.internal_defaults(),
        )


class RetrievalQualityEvaluator:
    def __init__(self, criteria: RetrievalQualityReviewCriteria):
        self.criteria = criteria

    def evaluate_suite(
        self,
        cases: list[RetrievalEvaluationCase],
    ) -> RetrievalQualitySummary:
        total_cases = len(cases)
        if total_cases == 0:
            return RetrievalQualitySummary(
                total_cases=0,
                passed_cases=0,
                fallback_cases=0,
                pass_rate=0.0,
                average_source_recall=0.0,
                top_hit_rate=0.0,
                passed=False,
            )

        passed_cases = 0
        fallback_cases = 0
        total_recall = 0.0
        top_hits = 0

        for case in cases:
            expected = set(case.expected_sources)
            retrieved = case.retrieved_sources
            retrieved_set = set(retrieved)
            matched = expected & retrieved_set

            recall = len(matched) / len(expected) if expected else 1.0
            total_recall += recall

            if matched:
                passed_cases += 1

            if expected and retrieved and retrieved[0] in expected:
                top_hits += 1

            if case.fallback_used:
                fallback_cases += 1

        pass_rate = passed_cases / total_cases
        average_source_recall = total_recall / total_cases
        top_hit_rate = top_hits / total_cases

        passed = (
            total_cases >= self.criteria.min_cases
            and pass_rate >= self.criteria.min_pass_rate
            and average_source_recall >= self.criteria.min_source_recall
            and top_hit_rate >= self.criteria.min_top_hit_rate
            and (
                not self.criteria.require_fallback_coverage
                or fallback_cases > 0
            )
        )

        return RetrievalQualitySummary(
            total_cases=total_cases,
            passed_cases=passed_cases,
            fallback_cases=fallback_cases,
            pass_rate=pass_rate,
            average_source_recall=average_source_recall,
            top_hit_rate=top_hit_rate,
            passed=passed,
        )
