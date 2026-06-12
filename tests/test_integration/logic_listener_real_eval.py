#!/usr/bin/env python3
"""
Standalone Real System Evaluation for Logic Listener
=====================================================

This script runs outside pytest to avoid conftest.py mock conflicts.
It uses real FastEmbed model for embedding-based off-topic detection.

Usage:
    python tests/test_integration/logic_listener_real_eval.py

Output: JSON with evaluation metrics
"""

import json
import time
import asyncio
import math
from pathlib import Path
from typing import Dict, List, Tuple, Any

# Import real modules (no mocks here)
from fastembed import TextEmbedding
from app.services.logic_listener import LogicListener, InterventionType

DATASET_PATH = (
    Path(__file__).parent.parent.parent
    / "data"
    / "evaluation"
    / "logic_listener_gold_standard.json"
)


class RealEmbeddingService:
    """Real embedding service using FastEmbed model."""

    def __init__(self):
        self._model = TextEmbedding(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )

    async def get_embedding(self, text: str) -> List[float]:
        embeddings = list(self._model.embed([text]))
        return embeddings[0].tolist()


def load_gold_standard() -> Dict[str, Any]:
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


def create_listener_with_real_embed() -> LogicListener:
    """Create LogicListener with real embedding service injected."""
    from unittest.mock import MagicMock, patch

    real_service = RealEmbeddingService()

    with (
        patch(
            "app.services.logic_listener.get_embedding_service",
            return_value=real_service,
        ),
        patch("app.services.logic_listener.get_mongo_logger", return_value=MagicMock()),
    ):
        return LogicListener()


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


def evaluate_silence(listener: LogicListener, data: Dict) -> Tuple[int, int, int]:
    items = [i for i in data["items"] if i["intervention_type"] == "silence"]
    tp = fp = fn = 0

    for item in items:
        inp = item["input"]
        group_id = inp["group_id"]
        expected = item["expected_should_intervene"]

        listener._last_message_timestamp[group_id] = (
            time.time() - inp["last_message_seconds_ago"]
        )
        predicted = listener.check_silence(group_id).should_intervene

        if predicted and expected:
            tp += 1
        elif predicted and not expected:
            fp += 1
        elif not predicted and expected:
            fn += 1

    return tp, fp, fn


def evaluate_participation_inequity(
    listener: LogicListener, data: Dict
) -> Tuple[int, int, int]:
    items = [
        i for i in data["items"] if i["intervention_type"] == "participation_inequity"
    ]
    tp = fp = fn = 0

    for item in items:
        inp = item["input"]
        group_id = inp["group_id"]
        expected = item["expected_should_intervene"]

        listener._participation_counts[group_id] = dict(inp["message_counts_per_user"])
        predicted = listener.check_participation_inequity(group_id).should_intervene

        if predicted and expected:
            tp += 1
        elif predicted and not expected:
            fp += 1
        elif not predicted and expected:
            fn += 1

    return tp, fp, fn


def main():
    print("Loading gold standard dataset...")
    data = load_gold_standard()

    print("Initializing LogicListener with real embedding model...")
    listener = create_listener_with_real_embed()

    # Warm up embedding model
    print("Warming up embedding model...")
    asyncio.run(listener.embedding_service.get_embedding("warmup"))

    print("Running evaluation...")

    # Off-topic
    off_tp, off_fp, off_fn = evaluate_off_topic(listener, data)
    off_p, off_r, off_f1 = compute_metrics(off_tp, off_fp, off_fn)

    # Silence
    sil_tp, sil_fp, sil_fn = evaluate_silence(listener, data)
    sil_p, sil_r, sil_f1 = compute_metrics(sil_tp, sil_fp, sil_fn)

    # Participation inequity
    ineq_tp, ineq_fp, ineq_fn = evaluate_participation_inequity(listener, data)
    ineq_p, ineq_r, ineq_f1 = compute_metrics(ineq_tp, ineq_fp, ineq_fn)

    # Macro average
    macro_p = round((off_p + sil_p + ineq_p) / 3, 4)
    macro_r = round((off_r + sil_r + ineq_r) / 3, 4)
    macro_f1 = round((off_f1 + sil_f1 + ineq_f1) / 3, 4)

    results = {
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
        "macro_average": {
            "precision": macro_p,
            "recall": macro_r,
            "f1": macro_f1,
        },
    }

    print("\n" + "=" * 72)
    print("  Logic Listener Real System Evaluation — Gold Standard Dataset")
    print("=" * 72)
    print(f"  {'Intervention Type':<30} {'Precision':>9} {'Recall':>8} {'F1':>8}")
    print("-" * 72)
    print(
        f"  {'Off-topic (real embed)':<30} {off_p:>9.4f} {off_r:>8.4f} {off_f1:>8.4f}"
    )
    print(
        f"  {'Silence (deterministic)':<30} {sil_p:>9.4f} {sil_r:>8.4f} {sil_f1:>8.4f}"
    )
    print(
        f"  {'Participation (deterministic)':<30} {ineq_p:>9.4f} {ineq_r:>8.4f} {ineq_f1:>8.4f}"
    )
    print("-" * 72)
    print(f"  {'Macro Average':<30} {macro_p:>9.4f} {macro_r:>8.4f} {macro_f1:>8.4f}")
    print("=" * 72 + "\n")

    # Output JSON for programmatic consumption
    print("---JSON_RESULTS---")
    print(json.dumps(results, indent=2))

    return results


if __name__ == "__main__":
    main()
