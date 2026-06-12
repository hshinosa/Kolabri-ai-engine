from __future__ import annotations

import pytest

from app.services.rag_quality import RetrievalQualityControls
from app.services.rag_retrieval_plan import RetrievalPlan, build_retrieval_plan


@pytest.fixture
def qc() -> RetrievalQualityControls:
    return RetrievalQualityControls(
        top_k_results=5,
        similarity_threshold=0.5,
        semantic_cache_threshold=0.95,
        reranking_enabled=True,
        rerank_top_k=5,
        rerank_retrieve_k=10,
        grounding_threshold=0.6,
    )


def test_default_plan_no_query_type(qc):
    plan = build_retrieval_plan(query="hi", query_type=None, quality_controls=qc)
    assert isinstance(plan, RetrievalPlan)
    assert plan.use_reranker is True
    assert plan.top_k == 10
    assert plan.score_threshold == pytest.approx(0.5)
    assert plan.rerank_top_n == 5
    assert plan.grounding_threshold == pytest.approx(0.6)


def test_factual_query_tightens_threshold_and_caps_rerank(qc):
    plan = build_retrieval_plan(
        query="when?", query_type="factual", quality_controls=qc
    )
    assert plan.score_threshold >= qc.similarity_threshold
    assert plan.rerank_top_n <= 3


def test_conceptual_query_loosens_threshold(qc):
    plan = build_retrieval_plan(
        query="why?", query_type="conceptual", quality_controls=qc
    )
    assert plan.score_threshold <= qc.similarity_threshold


def test_procedural_query_caps_rerank(qc):
    plan = build_retrieval_plan(
        query="how to", query_type="procedural", quality_controls=qc
    )
    assert plan.rerank_top_n <= 3


def test_plan_is_pure_no_io(qc):
    plan_a = build_retrieval_plan(query="x", query_type=None, quality_controls=qc)
    plan_b = build_retrieval_plan(query="x", query_type=None, quality_controls=qc)
    assert plan_a == plan_b


def test_requested_overrides_propagate(qc):
    plan = build_retrieval_plan(
        query="x",
        query_type=None,
        quality_controls=qc,
        requested_n_results=20,
        requested_score_threshold=0.3,
    )
    assert plan.top_k == 20
    assert plan.score_threshold == pytest.approx(0.3)
