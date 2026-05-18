from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Awaitable, Callable

from app.services.rag_benchmark_bootstrap import NormalizedBenchmarkCase


@dataclass(frozen=True)
class BenchmarkExecutionResult:
    case_id: str
    source_dataset: str
    benchmark_role: str
    retrieved_sources: list[str]
    generated_answer: str
    fallback_used: bool
    metrics: dict[str, float]


@dataclass(frozen=True)
class BenchmarkRunReport:
    total_cases: int
    datasets: dict[str, dict]
    report_path: Path


class RAGBenchmarkRunner:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    async def run(
        self,
        cases: list[NormalizedBenchmarkCase],
        executor: Callable[[NormalizedBenchmarkCase], Awaitable[BenchmarkExecutionResult]],
        report_name: str = "benchmark_report",
    ) -> BenchmarkRunReport:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        results = [await executor(case) for case in cases]

        datasets: dict[str, dict] = {}
        for result in results:
            dataset_entry = datasets.setdefault(
                result.source_dataset,
                {
                    "source_dataset": result.source_dataset,
                    "benchmark_roles": [],
                    "cases": 0,
                    "fallback_cases": 0,
                    "metrics": {},
                },
            )
            if result.benchmark_role not in dataset_entry["benchmark_roles"]:
                dataset_entry["benchmark_roles"].append(result.benchmark_role)
            dataset_entry["cases"] += 1
            dataset_entry["fallback_cases"] += 1 if result.fallback_used else 0
            for metric_name, metric_value in result.metrics.items():
                metric_list = dataset_entry["metrics"].setdefault(metric_name, [])
                metric_list.append(metric_value)

        for dataset_entry in datasets.values():
            dataset_entry["metrics"] = {
                metric_name: sum(values) / len(values)
                for metric_name, values in dataset_entry["metrics"].items()
            }
            dataset_entry["benchmark_roles"] = sorted(dataset_entry["benchmark_roles"])

        report_payload = {
            "generated_at": datetime.now(UTC).isoformat(),
            "execution_surface": "backend_only",
            "summary": {
                "total_cases": len(cases),
                "datasets": sorted(datasets.keys()),
            },
            "datasets": datasets,
            "results": [asdict(result) for result in results],
        }

        report_path = self.output_dir / f"{report_name}.json"
        report_path.write_text(json.dumps(report_payload, indent=2, ensure_ascii=False), encoding="utf-8")

        return BenchmarkRunReport(
            total_cases=len(cases),
            datasets=datasets,
            report_path=report_path,
        )
