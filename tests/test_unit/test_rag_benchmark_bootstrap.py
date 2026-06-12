from pathlib import Path

import pytest

from app.api.schemas import AskRequest, QueryRequest
from app.services.rag_benchmark_bootstrap import (
    BenchmarkDatasetBootstrap,
    BenchmarkWorkflow,
    NormalizedBenchmarkCase,
    PublicBenchmarkDatasetSource,
)


def test_approved_public_sources_are_fixed_and_backend_only():
    sources = BenchmarkDatasetBootstrap.approved_public_sources()

    assert [source.name for source in sources] == ["indoqa", "exams", "mirage"]
    assert all(source.backend_only for source in sources)
    assert {source.role for source in sources} == {
        "indonesian_qa_baseline",
        "educational_reasoning",
        "technical_rag_evaluation",
    }


def test_public_source_manifest_paths_exist():
    sources = BenchmarkDatasetBootstrap.approved_public_sources()

    for source in sources:
        assert source.manifest_path.exists(), f"missing manifest for {source.name}"


def test_normalize_public_case_preserves_provenance_and_role():
    source = PublicBenchmarkDatasetSource(
        name="indoqa",
        role="indonesian_qa_baseline",
        language="id",
        license="cc-by-nd-4.0",
        manifest_path=Path("/tmp/indoqa.json"),
        sample_path=Path("/tmp/indoqa_sample.json"),
        backend_only=True,
        source_format="context_qa",
    )

    case = BenchmarkDatasetBootstrap.normalize_public_case(
        source=source,
        raw_case={
            "id": "indoqa-1",
            "query": "Apa itu machine learning?",
            "answer": "Machine learning adalah cabang AI.",
            "contexts": ["Machine learning adalah cabang AI yang belajar dari data."],
        },
    )

    assert isinstance(case, NormalizedBenchmarkCase)
    assert case.source_dataset == "indoqa"
    assert case.benchmark_role == "indonesian_qa_baseline"
    assert case.expected_answer == "Machine learning adalah cabang AI."
    assert case.contexts == [
        "Machine learning adalah cabang AI yang belajar dari data."
    ]


def test_internal_placeholder_template_declares_future_kolabri_dataset_shape():
    template = BenchmarkDatasetBootstrap.internal_placeholder_template()

    assert template["source_dataset"] == "kolabri-internal-placeholder"
    assert template["benchmark_role"] == "future_course_document_rag"
    assert template["status"] == "template_only"
    assert "query" in template
    assert "expected_answer" in template
    assert "contexts" in template
    assert "expected_sources" in template


def test_get_public_source_unknown_raises():
    with pytest.raises(ValueError, match="Unknown benchmark"):
        BenchmarkDatasetBootstrap.get_public_source("not-a-real-source")


def test_backend_only_workflow_defers_public_execution_surfaces():
    workflow = BenchmarkDatasetBootstrap.backend_only_workflow()

    assert isinstance(workflow, BenchmarkWorkflow)
    assert workflow.execution_surface == "backend_only"
    assert "public_api_execution" in workflow.deferred_surfaces
    assert "admin_ops_benchmark_surface" in workflow.deferred_surfaces


def test_public_request_models_do_not_expose_benchmark_controls():
    query_fields = set(QueryRequest.model_fields.keys())
    ask_fields = set(AskRequest.model_fields.keys())

    forbidden = {"benchmark_dataset", "benchmark_role", "benchmark_case_id"}

    assert forbidden.isdisjoint(query_fields)
    assert forbidden.isdisjoint(ask_fields)
