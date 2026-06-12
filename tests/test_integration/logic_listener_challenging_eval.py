#!/usr/bin/env python3
"""
Challenging Dataset Evaluation with MPNet + Threshold Tuning
=============================================================

Evaluates Logic Listener on challenging dataset with subtle off-topic cases.
Auto-tunes threshold for MPNet model.

Usage:
    python tests/test_integration/logic_listener_challenging_eval.py
"""

import json
import time
import asyncio
import math
from pathlib import Path
from typing import Dict, List, Tuple, Any

from fastembed import TextEmbedding
from app.services.logic_listener import LogicListener, InterventionType

DATASET_PATH = (
    Path(__file__).parent.parent.parent
    / "data"
    / "evaluation"
    / "logic_listener_challenging.json"
)


class RealEmbeddingService:
    """Real embedding service using MPNet model."""

    def __init__(self):
        self._model = TextEmbedding(
            model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
        )

    async def get_embedding(self, text: str) -> List[float]:
        embeddings = list(self._model.embed([text]))
        return embeddings[0].tolist()


def create_listener_with_real_embed(threshold: float = 0.6) -> LogicListener:
    """Create LogicListener with real embedding service and custom threshold."""
    from unittest.mock import MagicMock, patch

    real_service = RealEmbeddingService()

    with (
        patch(
            "app.services.logic_listener.get_embedding_service",
            return_value=real_service,
        ),
        patch("app.services.logic_listener.get_mongo_logger", return_value=MagicMock()),
    ):
        listener = LogicListener()
        listener.off_topic_similarity_threshold = threshold
        return listener


def load_dataset() -> Dict[str, Any]:
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_metrics(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return round(precision, 4), round(recall, 4), round(f1, 4)


def evaluate_off_topic(listener: LogicListener, data: Dict) -> Tuple[int, int, int]:
    items = [i for i in data["items"] if i["intervention_type"] == "off_topic"]
    tp = fp = fn = 0

    for item in items:
        inp = item["input"]
        group_id = inp["group_id"]
        expected = item["expected_should_intervene"]

        asyncio.run(listener.set_group_topic(group_id, inp["course_topic"]))

        result = None
        for msg in inp["recent_messages"]:
            result = asyncio.run(listener.check_relevance(msg, group_id))

        predicted = result.should_intervene if result else False

        if predicted and expected:
            tp += 1
        elif predicted and not expected:
            fp += 1
        elif not predicted and expected:
            fn += 1

    return tp, fp, fn


def tune_threshold(data: Dict) -> Tuple[Dict[float, Dict], float]:
    """Auto-tune off-topic threshold from 0.4 to 0.8."""
    print("\n" + "=" * 72)
    print("  Threshold Tuning — Challenging Dataset (MPNet)")
    print("=" * 72)
    print(
        f"  {'Threshold':<10} {'TP':>4} {'FP':>4} {'FN':>4} {'Precision':>10} {'Recall':>8} {'F1':>8}"
    )
    print("-" * 72)

    results = {}
    best_f1 = 0.0
    best_threshold = 0.6

    for threshold in [0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8]:
        listener = create_listener_with_real_embed(threshold)
        asyncio.run(listener.embedding_service.get_embedding("warmup"))

        tp, fp, fn = evaluate_off_topic(listener, data)
        p, r, f1 = compute_metrics(tp, fp, fn)

        results[threshold] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": p,
            "recall": r,
            "f1": f1,
        }

        marker = " <-- BEST" if f1 > best_f1 else ""
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = threshold

        print(
            f"  {threshold:<10.2f} {tp:>4} {fp:>4} {fn:>4} {p:>10.4f} {r:>8.4f} {f1:>8.4f}{marker}"
        )

    print("=" * 72)
    print(f"\n  Best threshold: {best_threshold} (F1={best_f1:.4f})")

    return results, best_threshold


def evaluate_all(listener: LogicListener, data: Dict) -> Dict:
    """Evaluate all intervention types."""
    # Off-topic
    off_tp, off_fp, off_fn = evaluate_off_topic(listener, data)
    off_p, off_r, off_f1 = compute_metrics(off_tp, off_fp, off_fn)

    # Silence
    sil_items = [i for i in data["items"] if i["intervention_type"] == "silence"]
    sil_tp = sil_fp = sil_fn = 0
    for item in sil_items:
        inp = item["input"]
        listener._last_message_timestamp[inp["group_id"]] = (
            time.time() - inp["last_message_seconds_ago"]
        )
        predicted = listener.check_silence(inp["group_id"]).should_intervene
        expected = item["expected_should_intervene"]
        if predicted and expected:
            sil_tp += 1
        elif predicted and not expected:
            sil_fp += 1
        elif not predicted and expected:
            sil_fn += 1
    sil_p, sil_r, sil_f1 = compute_metrics(sil_tp, sil_fp, sil_fn)

    # Participation inequity
    ineq_items = [
        i for i in data["items"] if i["intervention_type"] == "participation_inequity"
    ]
    ineq_tp = ineq_fp = ineq_fn = 0
    for item in ineq_items:
        inp = item["input"]
        listener._participation_counts[inp["group_id"]] = dict(
            inp["message_counts_per_user"]
        )
        predicted = listener.check_participation_inequity(
            inp["group_id"]
        ).should_intervene
        expected = item["expected_should_intervene"]
        if predicted and expected:
            ineq_tp += 1
        elif predicted and not expected:
            ineq_fp += 1
        elif not predicted and expected:
            ineq_fn += 1
    ineq_p, ineq_r, ineq_f1 = compute_metrics(ineq_tp, ineq_fp, ineq_fn)

    macro_p = round((off_p + sil_p + ineq_p) / 3, 4)
    macro_r = round((off_r + sil_r + ineq_r) / 3, 4)
    macro_f1 = round((off_f1 + sil_f1 + ineq_f1) / 3, 4)

    return {
        "off_topic": {
            "tp": off_tp,
            "fp": off_fp,
            "fn": off_fn,
            "precision": off_p,
            "recall": off_r,
            "f1": off_f1,
        },
        "silence": {
            "tp": sil_tp,
            "fp": sil_fp,
            "fn": sil_fn,
            "precision": sil_p,
            "recall": sil_r,
            "f1": sil_f1,
        },
        "participation_inequity": {
            "tp": ineq_tp,
            "fp": ineq_fp,
            "fn": ineq_fn,
            "precision": ineq_p,
            "recall": ineq_r,
            "f1": ineq_f1,
        },
        "macro_average": {"precision": macro_p, "recall": macro_r, "f1": macro_f1},
    }


def main():
    print("Logic Listener Challenging Dataset Evaluation")
    print("Model: paraphrase-multilingual-mpnet-base-v2")
    print("=" * 72)

    data = load_dataset()
    print(f"Loaded challenging dataset: {len(data['items'])} items")

    # Step 1: Tune threshold
    tuning_results, best_threshold = tune_threshold(data)

    # Step 2: Evaluate with best threshold
    print("\n" + "=" * 72)
    print(f"  Final Evaluation — Threshold={best_threshold}")
    print("=" * 72)

    listener = create_listener_with_real_embed(best_threshold)
    asyncio.run(listener.embedding_service.get_embedding("warmup"))

    results = evaluate_all(listener, data)

    print(f"\n  Off-topic Detection:")
    print(
        f"    TP={results['off_topic']['tp']}, FP={results['off_topic']['fp']}, FN={results['off_topic']['fn']}"
    )
    print(
        f"    Precision={results['off_topic']['precision']:.4f}, Recall={results['off_topic']['recall']:.4f}, F1={results['off_topic']['f1']:.4f}"
    )

    print(f"\n  Silence Detection:")
    print(
        f"    TP={results['silence']['tp']}, FP={results['silence']['fp']}, FN={results['silence']['fn']}"
    )
    print(
        f"    Precision={results['silence']['precision']:.4f}, Recall={results['silence']['recall']:.4f}, F1={results['silence']['f1']:.4f}"
    )

    print(f"\n  Participation Inequity:")
    print(
        f"    TP={results['participation_inequity']['tp']}, FP={results['participation_inequity']['fp']}, FN={results['participation_inequity']['fn']}"
    )
    print(
        f"    Precision={results['participation_inequity']['precision']:.4f}, Recall={results['participation_inequity']['recall']:.4f}, F1={results['participation_inequity']['f1']:.4f}"
    )

    print(f"\n  Macro Average:")
    print(
        f"    Precision={results['macro_average']['precision']:.4f}, Recall={results['macro_average']['recall']:.4f}, F1={results['macro_average']['f1']:.4f}"
    )
    print("=" * 72)

    # Save results
    results_path = (
        Path(__file__).parent.parent.parent
        / "data"
        / "evaluation"
        / "logic_listener_challenging_results.json"
    )
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "model": "paraphrase-multilingual-mpnet-base-v2",
                "dataset": "logic_listener_challenging.json",
                "tuning": {str(k): v for k, v in tuning_results.items()},
                "optimal_threshold": best_threshold,
                "final_results": results,
            },
            f,
            indent=2,
        )
    print(f"\nResults saved to: {results_path}")


if __name__ == "__main__":
    main()
