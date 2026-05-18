import json
from pathlib import Path

import pytest

from app.services.rag_benchmark_bootstrap import BenchmarkDatasetBootstrap
from app.services.rag_benchmark_runner import (
    BenchmarkExecutionResult,
    RAGBenchmarkRunner,
)


def test_load_public_dataset_cases_normalizes_indoqa_exams_and_mirage():
    bootstrap = BenchmarkDatasetBootstrap()

    indoqa_cases = bootstrap.load_public_dataset_cases("indoqa")
    exams_cases = bootstrap.load_public_dataset_cases("exams")
    mirage_cases = bootstrap.load_public_dataset_cases("mirage")

    assert len(indoqa_cases) == 2
    assert len(exams_cases) == 2
    assert len(mirage_cases) == 2
    assert {case.source_dataset for case in indoqa_cases} == {"indoqa"}
    assert {case.source_dataset for case in exams_cases} == {"exams"}
    assert {case.source_dataset for case in mirage_cases} == {"mirage"}


@pytest.mark.asyncio
async def test_runner_executes_mixed_source_cases_and_preserves_provenance(tmp_path: Path):
    bootstrap = BenchmarkDatasetBootstrap()
    cases = [
        bootstrap.load_public_dataset_cases("indoqa")[0],
        bootstrap.load_public_dataset_cases("exams")[0],
        bootstrap.load_public_dataset_cases("mirage")[0],
    ]

    async def fake_executor(case):
        return BenchmarkExecutionResult(
            case_id=case.case_id,
            source_dataset=case.source_dataset,
            benchmark_role=case.benchmark_role,
            retrieved_sources=case.expected_sources or [f"{case.source_dataset}-source"],
            generated_answer=case.expected_answer,
            fallback_used=(case.source_dataset == "mirage"),
            metrics={"source_recall": 1.0, "answer_match": 1.0},
        )

    runner = RAGBenchmarkRunner(output_dir=tmp_path)
    report = await runner.run(cases, executor=fake_executor, report_name="smoke")

    assert report.total_cases == 3
    assert set(report.datasets.keys()) == {"indoqa", "exams", "mirage"}
    assert report.datasets["mirage"]["fallback_cases"] == 1
    assert report.report_path.exists()

    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert payload["summary"]["total_cases"] == 3
    assert payload["datasets"]["indoqa"]["benchmark_roles"] == ["indonesian_qa_baseline"]


@pytest.mark.asyncio
async def test_runner_report_includes_provenance_and_backend_only_metadata(tmp_path: Path):
    case = BenchmarkDatasetBootstrap.load_public_dataset_cases("indoqa")[0]

    async def fake_executor(_case):
        return BenchmarkExecutionResult(
            case_id=_case.case_id,
            source_dataset=_case.source_dataset,
            benchmark_role=_case.benchmark_role,
            retrieved_sources=_case.expected_sources,
            generated_answer=_case.expected_answer,
            fallback_used=False,
            metrics={"source_recall": 1.0},
        )

    runner = RAGBenchmarkRunner(output_dir=tmp_path)
    report = await runner.run([case], executor=fake_executor, report_name="single")

    payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    assert payload["execution_surface"] == "backend_only"
    assert payload["datasets"]["indoqa"]["source_dataset"] == "indoqa"
    assert payload["datasets"]["indoqa"]["benchmark_roles"] == ["indonesian_qa_baseline"]
