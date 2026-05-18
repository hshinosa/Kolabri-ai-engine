import pytest

from app.services.rag_quality import (
    InternalRetrievalQualityWorkflow,
    RetrievalEvaluationCase,
    RetrievalQualityEvaluator,
    RetrievalQualityReviewCriteria,
    RetrievalQualityControls,
)
from app.api.schemas import AskRequest, QueryRequest


def test_retrieval_quality_controls_from_settings():
    controls = RetrievalQualityControls.from_settings()

    assert controls.top_k_results >= 1
    assert 0 <= controls.similarity_threshold <= 1
    assert controls.rerank_retrieve_k >= controls.rerank_top_k


def test_resolve_search_plan_expands_results_for_reranking():
    controls = RetrievalQualityControls(
        top_k_results=5,
        similarity_threshold=0.6,
        semantic_cache_threshold=0.85,
        reranking_enabled=True,
        rerank_top_k=3,
        rerank_retrieve_k=10,
        grounding_threshold=0.4,
    )

    plan = controls.resolve_search_plan(requested_n_results=3)

    assert plan.output_n_results == 3
    assert plan.search_n_results == 10
    assert plan.score_threshold == 0.6
    assert plan.reranking_enabled is True


def test_resolve_search_plan_honors_explicit_threshold_override():
    controls = RetrievalQualityControls(
        top_k_results=5,
        similarity_threshold=0.6,
        semantic_cache_threshold=0.85,
        reranking_enabled=False,
        rerank_top_k=3,
        rerank_retrieve_k=10,
        grounding_threshold=0.4,
    )

    plan = controls.resolve_search_plan(requested_n_results=2, score_threshold=0.73)

    assert plan.search_n_results == 2
    assert plan.output_n_results == 2
    assert plan.score_threshold == 0.73
    assert plan.reranking_enabled is False


def test_evaluate_suite_passes_with_fallback_coverage():
    criteria = RetrievalQualityReviewCriteria(
        min_cases=2,
        min_pass_rate=0.5,
        min_source_recall=0.5,
        min_top_hit_rate=0.5,
        require_fallback_coverage=True,
    )
    evaluator = RetrievalQualityEvaluator(criteria)

    summary = evaluator.evaluate_suite(
        [
            RetrievalEvaluationCase(
                query="What is retrieval?",
                expected_sources=["doc-a", "doc-b"],
                retrieved_sources=["doc-a", "doc-c"],
                fallback_used=False,
            ),
            RetrievalEvaluationCase(
                query="Fallback case",
                expected_sources=["doc-z"],
                retrieved_sources=["doc-z"],
                fallback_used=True,
            ),
        ]
    )

    assert summary.passed is True
    assert summary.fallback_cases == 1
    assert summary.total_cases == 2
    assert summary.top_hit_rate >= 0.5


def test_evaluate_suite_fails_without_required_fallback_case():
    criteria = RetrievalQualityReviewCriteria(
        min_cases=1,
        min_pass_rate=0.0,
        min_source_recall=0.0,
        min_top_hit_rate=0.0,
        require_fallback_coverage=True,
    )
    evaluator = RetrievalQualityEvaluator(criteria)

    summary = evaluator.evaluate_suite(
        [
            RetrievalEvaluationCase(
                query="No fallback case",
                expected_sources=["doc-a"],
                retrieved_sources=["doc-a"],
                fallback_used=False,
            ),
        ]
    )

    assert summary.passed is False
    assert summary.fallback_cases == 0


def test_internal_review_workflow_from_settings_exposes_backend_only_defaults():
    workflow = InternalRetrievalQualityWorkflow.from_settings()

    assert workflow.controls.top_k_results >= 1
    assert workflow.criteria.min_cases >= 1
    assert "public_api_request_parameters" in workflow.deferred_surfaces
    assert "admin_ops_runtime_endpoints" in workflow.deferred_surfaces


def test_public_request_models_do_not_expose_runtime_tuning_fields():
    query_fields = set(QueryRequest.model_fields.keys())
    ask_fields = set(AskRequest.model_fields.keys())

    forbidden = {"score_threshold", "enable_reranking", "rerank_top_k", "rerank_retrieve_k"}

    assert forbidden.isdisjoint(query_fields)
    assert forbidden.isdisjoint(ask_fields)
