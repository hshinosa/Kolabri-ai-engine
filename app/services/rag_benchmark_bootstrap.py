from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PublicBenchmarkDatasetSource:
    name: str
    role: str
    language: str
    license: str
    manifest_path: Path
    sample_path: Path
    backend_only: bool
    source_format: str


@dataclass(frozen=True)
class NormalizedBenchmarkCase:
    case_id: str
    source_dataset: str
    benchmark_role: str
    query: str
    expected_answer: str
    contexts: list[str]
    expected_sources: list[str]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class BenchmarkWorkflow:
    execution_surface: str
    deferred_surfaces: tuple[str, ...]


class BenchmarkDatasetBootstrap:
    @staticmethod
    def _benchmarks_root() -> Path:
        return Path(__file__).resolve().parents[2] / "data" / "benchmarks"

    @classmethod
    def approved_public_sources(cls) -> list[PublicBenchmarkDatasetSource]:
        root = cls._benchmarks_root() / "public"
        return [
            PublicBenchmarkDatasetSource(
                name="indoqa",
                role="indonesian_qa_baseline",
                language="id",
                license="cc-by-nd-4.0",
                manifest_path=root / "indoqa_manifest.json",
                sample_path=root / "indoqa_sample.json",
                backend_only=True,
                source_format="context_qa",
            ),
            PublicBenchmarkDatasetSource(
                name="exams",
                role="educational_reasoning",
                language="multilingual",
                license="cc-by-sa-4.0",
                manifest_path=root / "exams_manifest.json",
                sample_path=root / "exams_sample.json",
                backend_only=True,
                source_format="exam_qa",
            ),
            PublicBenchmarkDatasetSource(
                name="mirage",
                role="technical_rag_evaluation",
                language="en",
                license="apache-2.0",
                manifest_path=root / "mirage_manifest.json",
                sample_path=root / "mirage_sample.json",
                backend_only=True,
                source_format="rag_eval",
            ),
        ]

    @classmethod
    def get_public_source(cls, name: str) -> PublicBenchmarkDatasetSource:
        for source in cls.approved_public_sources():
            if source.name == name:
                return source
        raise ValueError(f"Unknown benchmark dataset source: {name}")

    @staticmethod
    def normalize_public_case(
        source: PublicBenchmarkDatasetSource,
        raw_case: dict[str, Any],
    ) -> NormalizedBenchmarkCase:
        return NormalizedBenchmarkCase(
            case_id=str(raw_case.get("id") or raw_case.get("case_id") or "unknown-case"),
            source_dataset=source.name,
            benchmark_role=source.role,
            query=str(raw_case["query"]),
            expected_answer=str(raw_case.get("answer") or raw_case.get("expected_answer") or ""),
            contexts=[str(item) for item in raw_case.get("contexts", [])],
            expected_sources=[str(item) for item in raw_case.get("expected_sources", [])],
            metadata={
                "language": source.language,
                "license": source.license,
                "source_format": source.source_format,
                "backend_only": source.backend_only,
                "source_dataset": source.name,
                "benchmark_role": source.role,
                **raw_case.get("metadata", {}),
            },
        )

    @classmethod
    def load_public_dataset_cases(cls, name: str) -> list[NormalizedBenchmarkCase]:
        source = cls.get_public_source(name)
        payload = json.loads(source.sample_path.read_text(encoding="utf-8"))
        return [cls.normalize_public_case(source, raw_case) for raw_case in payload]

    @classmethod
    def internal_placeholder_template(cls) -> dict[str, Any]:
        return {
            "source_dataset": "kolabri-internal-placeholder",
            "benchmark_role": "future_course_document_rag",
            "status": "template_only",
            "query": "",
            "expected_answer": "",
            "contexts": [],
            "expected_sources": [],
            "metadata": {
                "course_id": "",
                "document_ids": [],
                "notes": "Populate when Kolabri-native benchmark data becomes available.",
            },
        }

    @staticmethod
    def backend_only_workflow() -> BenchmarkWorkflow:
        return BenchmarkWorkflow(
            execution_surface="backend_only",
            deferred_surfaces=(
                "public_api_execution",
                "admin_ops_benchmark_surface",
            ),
        )
