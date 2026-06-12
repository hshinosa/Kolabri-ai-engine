#!/usr/bin/env python3
"""
A/B retrieval eval: vector search only vs vector + cross-encoder rerank (P@3, MRR@5).

Dataset: data/evaluation/rag_evaluation_dataset.json (same as run_rag_evaluation.py)
Output:  data/evaluation/performance/rerank_ablation_YYYYMMDD_HHMMSS.json

Usage:
  cd Kolabri-ai-engine && source .venv/bin/activate
  python scripts/reproduce_rerank_ablation.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, UTC
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import structlog

structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(50))

from app.core.config import settings
from app.services.vector_store import get_vector_store
from app.services.reranker import CrossEncoderReranker, CROSS_ENCODER_AVAILABLE

DATASET = ROOT / "data" / "evaluation" / "rag_evaluation_dataset.json"
COLLECTION = "course_eval"
RETRIEVE_K = settings.RERANK_RETRIEVE_K
TOP_K = settings.RERANK_TOP_K


def _is_relevant(item: dict, doc: dict) -> bool:
    needle = item["expected_source_contains"].lower()
    meta = doc.get("metadata") or {}
    source = str(meta.get("source", meta.get("document_id", ""))).lower()
    content = str(doc.get("content", "")).lower()
    return needle in source or needle in content


def _metrics_for_ranking(item: dict, ranked: list[dict]) -> tuple[float, float]:
    relevant_ranks = [i + 1 for i, d in enumerate(ranked) if _is_relevant(item, d)]
    mrr = 1.0 / relevant_ranks[0] if relevant_ranks else 0.0
    p3 = sum(1 for d in ranked[:3] if _is_relevant(item, d)) / 3.0
    return mrr, p3


async def evaluate_without_rerank(items: list[dict]) -> dict:
    vs = get_vector_store()
    mrrs, p3s = [], []
    for item in items:
        try:
            hits = await vs.search(
                query=item["query"],
                collection_name=COLLECTION,
                n_results=RETRIEVE_K,
                score_threshold=0.0,
            )
            docs = [
                {
                    "content": h["content"],
                    "metadata": h.get("metadata", {}),
                    "score": h.get("score"),
                }
                for h in hits
            ]
            mrr, p3 = _metrics_for_ranking(item, docs)
        except Exception:
            mrr, p3 = 0.0, 0.0
        mrrs.append(mrr)
        p3s.append(p3)
    return {
        "mode": "vector_only",
        "mrr_at_5": round(sum(mrrs) / len(mrrs), 4) if mrrs else 0.0,
        "precision_at_3": round(sum(p3s) / len(p3s), 4) if p3s else 0.0,
        "n_queries": len(items),
    }


async def evaluate_with_rerank(
    items: list[dict], reranker: CrossEncoderReranker
) -> dict:
    vs = get_vector_store()
    await reranker.load_model()
    mrrs, p3s = [], []
    for item in items:
        try:
            hits = await vs.search(
                query=item["query"],
                collection_name=COLLECTION,
                n_results=RETRIEVE_K,
                score_threshold=0.0,
            )
            docs = [
                {
                    "content": h["content"],
                    "metadata": h.get("metadata", {}),
                    "score": h.get("score"),
                }
                for h in hits
            ]
            if reranker.enabled and docs:
                docs = await reranker.rerank(item["query"], docs, top_k=TOP_K)
            mrr, p3 = _metrics_for_ranking(item, docs)
        except Exception:
            mrr, p3 = 0.0, 0.0
        mrrs.append(mrr)
        p3s.append(p3)
    return {
        "mode": "vector_plus_rerank",
        "rerank_model": settings.RERANK_MODEL_NAME,
        "rerank_enabled_runtime": reranker.enabled,
        "mrr_at_5": round(sum(mrrs) / len(mrrs), 4) if mrrs else 0.0,
        "precision_at_3": round(sum(p3s) / len(p3s), 4) if p3s else 0.0,
        "n_queries": len(items),
    }


async def main() -> int:
    if not DATASET.exists():
        print(f"Missing dataset: {DATASET}")
        return 1

    payload = json.loads(DATASET.read_text(encoding="utf-8"))
    items = payload.get("items") or payload.get("queries") or []
    if not items:
        print("Dataset has no items")
        return 1

    out_dir = ROOT / "data" / "evaluation" / "performance"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"rerank_ablation_{stamp}.json"

    baseline = await evaluate_without_rerank(items)
    reranker = CrossEncoderReranker(
        model_name=settings.RERANK_MODEL_NAME,
        top_k=TOP_K,
        retrieve_k=RETRIEVE_K,
    )
    reranker.enabled = settings.ENABLE_RERANKING and CROSS_ENCODER_AVAILABLE
    with_rerank = await evaluate_with_rerank(items, reranker)

    delta_p3 = round(with_rerank["precision_at_3"] - baseline["precision_at_3"], 4)
    delta_mrr = round(with_rerank["mrr_at_5"] - baseline["mrr_at_5"], 4)

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": str(DATASET.relative_to(ROOT)),
        "collection": COLLECTION,
        "retrieve_k": RETRIEVE_K,
        "rerank_top_k": TOP_K,
        "fastembed_available": CROSS_ENCODER_AVAILABLE,
        "baseline_vector_only": baseline,
        "with_cross_encoder_rerank": with_rerank,
        "delta": {
            "precision_at_3": delta_p3,
            "mrr_at_5": delta_mrr,
        },
        "note": (
            "Compare to Bab4 rerank P@3 claims only if same dataset/collection populated. "
            "TA model name may differ (ms-marco vs jina)."
        ),
    }

    out_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
