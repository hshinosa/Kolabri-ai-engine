import sys
import json
import asyncio
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(50))

from app.services.vector_store import get_vector_store
from app.services.llm import get_llm_service

DATASET_PATH = Path("data/evaluation/rag_evaluation_dataset.json")
RESULTS_PATH = Path("data/evaluation/rag_evaluation_results.md")


def load_dataset(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def keyword_coverage(answer: str, keywords: List[str]) -> float:
    answer_lower = answer.lower()
    matched = sum(1 for kw in keywords if kw.lower() in answer_lower)
    return matched / len(keywords) if keywords else 0.0


async def run_retrieval_evaluation(items: List[Dict]) -> Dict[str, Any]:
    vector_store = get_vector_store()
    mrr_scores = []
    precision_scores = []

    for item in items:
        try:
            results = await vector_store.search(
                query=item["query"],
                collection_name="course_eval",
                n_results=5,
                score_threshold=0.0,
            )
            expected = item["expected_source_contains"].lower()

            relevant_ranks = [
                i + 1 for i, r in enumerate(results)
                if expected in str(r.get("source", "")).lower()
                or expected in str(r.get("content", "")).lower()
            ]

            mrr = 1.0 / relevant_ranks[0] if relevant_ranks else 0.0
            precision_at_3 = sum(
                1 for r in results[:3]
                if expected in str(r.get("source", "")).lower()
                or expected in str(r.get("content", "")).lower()
            ) / 3.0

            mrr_scores.append(mrr)
            precision_scores.append(precision_at_3)
        except Exception:
            mrr_scores.append(0.0)
            precision_scores.append(0.0)

    return {
        "mrr_at_5": round(sum(mrr_scores) / len(mrr_scores), 4) if mrr_scores else 0.0,
        "precision_at_3": round(sum(precision_scores) / len(precision_scores), 4) if precision_scores else 0.0,
        "per_item": list(zip([i["id"] for i in items], mrr_scores, precision_scores)),
    }


async def run_no_rag_evaluation(items: List[Dict]) -> Dict[str, Any]:
    llm = get_llm_service()
    coverage_scores = []

    for item in items:
        try:
            prompt = f"Pertanyaan: {item['query']}\n\nJawaban:"
            response = await llm.generate(prompt, max_tokens=400)
            if response.success and response.content:
                coverage = keyword_coverage(response.content, item["expected_answer_keywords"])
            else:
                coverage = 0.0
            coverage_scores.append(coverage)
        except Exception:
            coverage_scores.append(0.0)

    return {
        "keyword_coverage": round(sum(coverage_scores) / len(coverage_scores) * 100, 2) if coverage_scores else 0.0,
        "per_item": list(zip([i["id"] for i in items], coverage_scores)),
    }

async def run_answer_evaluation(items: List[Dict]) -> Dict[str, Any]:
    vector_store = get_vector_store()
    llm = get_llm_service()
    coverage_scores = []

    for item in items:
        try:
            docs = await vector_store.search(
                query=item["query"],
                collection_name="course_eval",
                n_results=5,
                score_threshold=0.0,
            )
            context = "\n\n".join([d.get("content", "") for d in docs[:3]])
            prompt = (
                f"Berdasarkan konteks berikut, jawab pertanyaan dengan jelas dan lengkap.\n\n"
                f"Konteks:\n{context[:2000]}\n\n"
                f"Pertanyaan: {item['query']}\n\nJawaban:"
            )
            response = await llm.generate(prompt, max_tokens=400)
            if response.success and response.content:
                coverage = keyword_coverage(response.content, item["expected_answer_keywords"])
            else:
                coverage = 0.0
            coverage_scores.append(coverage)
        except Exception:
            coverage_scores.append(0.0)

    return {
        "keyword_coverage": round(sum(coverage_scores) / len(coverage_scores) * 100, 2) if coverage_scores else 0.0,
        "per_item": list(zip([i["id"] for i in items], coverage_scores)),
    }


def compute_per_type_metrics(
    items: List[Dict],
    retrieval_per_item: List[Tuple],
    answer_per_item: List[Tuple],
) -> Dict[str, Dict]:
    id_to_retrieval = {r[0]: (r[1], r[2]) for r in retrieval_per_item}
    id_to_coverage = {r[0]: r[1] for r in answer_per_item}

    by_type: Dict[str, Dict] = {}
    for item in items:
        qtype = item["query_type"]
        if qtype not in by_type:
            by_type[qtype] = {"mrr": [], "p3": [], "cov": []}
        item_id = item["id"]
        mrr, p3 = id_to_retrieval.get(item_id, (0.0, 0.0))
        cov = id_to_coverage.get(item_id, 0.0)
        by_type[qtype]["mrr"].append(mrr)
        by_type[qtype]["p3"].append(p3)
        by_type[qtype]["cov"].append(cov)

    return {
        qtype: {
            "mrr_at_5": round(sum(v["mrr"]) / len(v["mrr"]), 4),
            "precision_at_3": round(sum(v["p3"]) / len(v["p3"]), 4),
            "keyword_coverage_pct": round(sum(v["cov"]) / len(v["cov"]) * 100, 2),
        }
        for qtype, v in by_type.items()
    }


def print_results_table(
    retrieval: Dict,
    answer: Dict,
    no_rag: Dict,
    per_type: Dict,
    dataset_size: int,
) -> None:
    improvement = answer["keyword_coverage"] - no_rag["keyword_coverage"]
    print("\n" + "=" * 65)
    print("  RAG Evaluation Results — RAG vs No-RAG Baseline")
    print("=" * 65)
    print(f"  Dataset: {dataset_size} queries\n")
    print("  Retrieval Metrics (RAG):")
    print(f"    MRR@5:        {retrieval['mrr_at_5']:.4f}")
    print(f"    Precision@3:  {retrieval['precision_at_3']:.4f}\n")
    print("  Answer Quality Comparison:")
    print(f"    {'':30} {'RAG':>8}  {'No-RAG':>8}  {'Delta':>8}")
    print(f"    {'Keyword Coverage':<30} {answer['keyword_coverage']:>7.1f}%  {no_rag['keyword_coverage']:>7.1f}%  {improvement:>+7.1f}%\n")
    print("  Per Query Type (RAG):")
    print(f"  {'Type':<14} {'MRR@5':>8} {'P@3':>8} {'Coverage':>10}")
    print("  " + "-" * 44)
    for qtype, metrics in per_type.items():
        print(
            f"  {qtype:<14} {metrics['mrr_at_5']:>8.4f} "
            f"{metrics['precision_at_3']:>8.4f} "
            f"{metrics['keyword_coverage_pct']:>9.1f}%"
        )
    print("=" * 65 + "\n")


def save_results(
    retrieval: Dict,
    answer: Dict,
    no_rag: Dict,
    per_type: Dict,
    dataset_size: int,
    path: Path,
) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    improvement = answer["keyword_coverage"] - no_rag["keyword_coverage"]
    lines = [
        f"# RAG Evaluation Results\n",
        f"**Date:** {timestamp}  ",
        f"**Dataset:** `data/evaluation/rag_evaluation_dataset.json` ({dataset_size} queries)\n",
        "## Overall Metrics\n",
        "| Metric | RAG | No-RAG | Delta |",
        "|--------|-----|--------|-------|",
        f"| MRR@5 | {retrieval['mrr_at_5']:.4f} | — | — |",
        f"| Precision@3 | {retrieval['precision_at_3']:.4f} | — | — |",
        f"| Keyword Coverage | {answer['keyword_coverage']:.1f}% | {no_rag['keyword_coverage']:.1f}% | {improvement:+.1f}% |\n",
        "## Per Query Type (RAG)\n",
        "| Query Type | MRR@5 | Precision@3 | Keyword Coverage |",
        "|------------|-------|-------------|-----------------|",
    ]
    for qtype, metrics in per_type.items():
        lines.append(
            f"| {qtype} | {metrics['mrr_at_5']:.4f} | "
            f"{metrics['precision_at_3']:.4f} | "
            f"{metrics['keyword_coverage_pct']:.1f}% |"
        )
    lines += [
        "\n## LaTeX Table (untuk Bab 4)\n",
        "```latex",
        "\\begin{table}[h]",
        "\\centering",
        "\\caption{Perbandingan Kualitas Jawaban RAG vs Tanpa RAG}",
        "\\label{tab:rag-baseline}",
        "\\begin{tabular}{lccc}",
        "\\hline",
        "\\textbf{Metrik} & \\textbf{RAG} & \\textbf{Tanpa RAG} & \\textbf{Peningkatan} \\\\",
        "\\hline",
        f"MRR@5 & {retrieval['mrr_at_5']:.4f} & — & — \\\\",
        f"Precision@3 & {retrieval['precision_at_3']:.4f} & — & — \\\\",
        f"Keyword Coverage & {answer['keyword_coverage']:.1f}\\% & {no_rag['keyword_coverage']:.1f}\\% & {improvement:+.1f}\\% \\\\",
        "\\hline",
        "\\end{tabular}",
        "\\end{table}",
        "```",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Results saved to {path}")


async def main(dataset_path: Path, save: bool) -> None:
    data = load_dataset(dataset_path)
    items = data["items"]

    print(f"Running RAG evaluation on {len(items)} queries...")

    retrieval = await run_retrieval_evaluation(items)
    answer = await run_answer_evaluation(items)
    no_rag = await run_no_rag_evaluation(items)
    per_type = compute_per_type_metrics(
        items,
        retrieval["per_item"],
        answer["per_item"],
    )

    print_results_table(retrieval, answer, no_rag, per_type, len(items))

    if save:
        save_results(retrieval, answer, no_rag, per_type, len(items), RESULTS_PATH)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate RAG pipeline against gold standard dataset")
    parser.add_argument("--save-results", action="store_true", help="Save results to data/evaluation/rag_evaluation_results.md")
    parser.add_argument("--dataset-path", type=Path, default=DATASET_PATH, help="Path to evaluation dataset JSON")
    args = parser.parse_args()

    asyncio.run(main(args.dataset_path, args.save_results))
