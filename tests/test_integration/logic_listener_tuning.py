#!/usr/bin/env python3
"""
Logic Listener Threshold Tuning & Dataset Expansion
====================================================

1. Auto-tune off-topic similarity threshold (0.5 - 0.7)
2. Generate synthetic dataset expansion with edge cases
3. Re-evaluate with optimal threshold + expanded dataset

Usage:
    python tests/test_integration/logic_listener_tuning.py
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
    / "logic_listener_gold_standard.json"
)

EXPANDED_DATASET_PATH = (
    Path(__file__).parent.parent.parent
    / "data"
    / "evaluation"
    / "logic_listener_gold_standard_expanded.json"
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


def tune_threshold(data: Dict) -> Dict[float, Dict]:
    """Auto-tune off-topic threshold from 0.5 to 0.7."""
    print("\n" + "=" * 72)
    print("  Threshold Tuning — Off-topic Detection")
    print("=" * 72)
    print(
        f"  {'Threshold':<10} {'TP':>4} {'FP':>4} {'FN':>4} {'Precision':>10} {'Recall':>8} {'F1':>8}"
    )
    print("-" * 72)

    results = {}
    best_f1 = 0.0
    best_threshold = 0.6

    for threshold in [0.5, 0.55, 0.6, 0.65, 0.7]:
        listener = create_listener_with_real_embed(threshold)
        # Warm up
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


def generate_synthetic_dataset(base_data: Dict) -> Dict:
    """Generate expanded synthetic dataset with edge cases."""
    print("\n" + "=" * 72)
    print("  Generating Synthetic Dataset Expansion")
    print("=" * 72)

    new_items = []
    item_id = 31

    # Edge case 1: Mixed-topic messages (partially relevant)
    mixed_topic_cases = [
        {
            "topic": "Pemrograman Web dengan HTML, CSS, dan JavaScript",
            "messages": [
                "Gimana cara bikin form login yang secure?",
                "Bisa pakai JWT atau session-based",
                "Eh btw tadi makan siang dimana?",
            ],
            "should_intervene": False,  # 2/3 relevant, not consecutive off-topic
            "rationale": "2 pesan relevan, 1 pesan off-topic di akhir. Counter reset setelah pesan relevan.",
        },
        {
            "topic": "Algoritma dan Struktur Data",
            "messages": [
                "Quick sort itu divide and conquer kan?",
                "Iya, tapi kemarin aku nonton film tentang hacker",
                "Filmnya seru gak?",
            ],
            "should_intervene": False,  # First message resets counter
            "rationale": "Pesan pertama relevan, reset counter. 2 pesan off-topic tidak cukup untuk trigger.",
        },
        {
            "topic": "Basis Data dan SQL",
            "messages": [
                "Liburan semester ini pada kemana?",
                "Aku mau ke Bali",
                "Eh btw, INNER JOIN itu gimana sih?",
            ],
            "should_intervene": False,  # Last message resets counter
            "rationale": "2 pesan off-topic, tapi pesan ketiga relevan dan reset counter.",
        },
        {
            "topic": "Jaringan Komputer dan Protokol TCP/IP",
            "messages": [
                "TCP itu connection-oriented ya?",
                "Iya, ada three-way handshake",
                "Handshake itu kaya salaman gak sih?",
            ],
            "should_intervene": False,  # Metaphor is still on-topic
            "rationale": "Pesan ketiga adalah metafora tentang handshake dalam konteks TCP, masih relevan.",
        },
        {
            "topic": "Kecerdasan Buatan dan Machine Learning",
            "messages": [
                "Overfitting itu apa ya?",
                "Kayak kita belajar tapi hafalan doang",
                "Iya, jadi gak bisa generalisasi",
            ],
            "should_intervene": False,  # Analogies are on-topic
            "rationale": "Analogi dan penjelasan konsep ML menggunakan bahasa sehari-hari, masih relevan.",
        },
    ]

    for case in mixed_topic_cases:
        new_items.append(
            {
                "id": f"off_topic_{item_id:03d}",
                "intervention_type": "off_topic",
                "expected_should_intervene": case["should_intervene"],
                "input": {
                    "group_id": f"group_eval_{item_id:02d}",
                    "course_topic": case["topic"],
                    "recent_messages": case["messages"],
                    "message_count": len(case["messages"]),
                },
                "labeling_rationale": case["rationale"],
            }
        )
        item_id += 1

    # Edge case 2: Subtle off-topic (related but not course-specific)
    subtle_off_topic = [
        {
            "topic": "Pemrograman Web dengan HTML, CSS, dan JavaScript",
            "messages": [
                "React itu framework JavaScript kan?",
                "Iya, dibuat oleh Facebook",
                "Facebook sekarang jadi Meta ya?",
            ],
            "should_intervene": True,  # Drift to company history
            "rationale": "Pesan ketiga drift ke sejarah perusahaan, tidak relevan dengan pemrograman web.",
        },
        {
            "topic": "Algoritma dan Struktur Data",
            "messages": [
                "Binary search itu O(log n) kan?",
                "Iya, tapi implementasinya tricky",
                "Tricky itu bahasa Inggris ya?",
            ],
            "should_intervene": True,  # Language discussion
            "rationale": "Pesan ketiga membahas etimologi bahasa, tidak relevan dengan algoritma.",
        },
        {
            "topic": "Basis Data dan SQL",
            "messages": [
                "Normalization itu penting gak?",
                "Penting banget, reduce redundancy",
                "Redundancy itu artinya berlebihan kan?",
            ],
            "should_intervene": True,  # Dictionary definition
            "rationale": "Pesan ketiga membahas definisi kata, bukan konsep database.",
        },
    ]

    for case in subtle_off_topic:
        new_items.append(
            {
                "id": f"off_topic_{item_id:03d}",
                "intervention_type": "off_topic",
                "expected_should_intervene": case["should_intervene"],
                "input": {
                    "group_id": f"group_eval_{item_id:02d}",
                    "course_topic": case["topic"],
                    "recent_messages": case["messages"],
                    "message_count": len(case["messages"]),
                },
                "labeling_rationale": case["rationale"],
            }
        )
        item_id += 1

    # Edge case 3: Code-heavy on-topic messages
    code_on_topic = [
        {
            "topic": "Pemrograman Web dengan HTML, CSS, dan JavaScript",
            "messages": [
                "```javascript\nconst x = 10;\n```",
                "```css\n.display { flex }\n```",
                "```html\n<div>Hello</div>\n```",
            ],
            "should_intervene": False,
            "rationale": "Pesan berisi code snippet yang relevan dengan pemrograman web.",
        },
        {
            "topic": "Algoritma dan Struktur Data",
            "messages": [
                "```python\ndef quicksort(arr):\n    if len(arr) <= 1: return arr\n```",
                "```python\npivot = arr[len(arr) // 2]\n```",
                "```python\nreturn quicksort(left) + middle + quicksort(right)\n```",
            ],
            "should_intervene": False,
            "rationale": "Pesan berisi implementasi algoritma quicksort, sangat relevan.",
        },
    ]

    for case in code_on_topic:
        new_items.append(
            {
                "id": f"off_topic_{item_id:03d}",
                "intervention_type": "off_topic",
                "expected_should_intervene": case["should_intervene"],
                "input": {
                    "group_id": f"group_eval_{item_id:02d}",
                    "course_topic": case["topic"],
                    "recent_messages": case["messages"],
                    "message_count": len(case["messages"]),
                },
                "labeling_rationale": case["rationale"],
            }
        )
        item_id += 1

    # Edge case 4: Very short messages
    short_messages = [
        {
            "topic": "Pemrograman Web dengan HTML, CSS, dan JavaScript",
            "messages": ["Ok", "Siap", "Mantap"],
            "should_intervene": True,
            "rationale": "3 pesan sangat pendek tanpa substansi, tidak relevan dengan topik.",
        },
        {
            "topic": "Basis Data dan SQL",
            "messages": ["Yes", "No", "Maybe"],
            "should_intervene": True,
            "rationale": "3 pesan sangat pendek tanpa konten akademik.",
        },
    ]

    for case in short_messages:
        new_items.append(
            {
                "id": f"off_topic_{item_id:03d}",
                "intervention_type": "off_topic",
                "expected_should_intervene": case["should_intervene"],
                "input": {
                    "group_id": f"group_eval_{item_id:02d}",
                    "course_topic": case["topic"],
                    "recent_messages": case["messages"],
                    "message_count": len(case["messages"]),
                },
                "labeling_rationale": case["rationale"],
            }
        )
        item_id += 1

    # Edge case 5: Bahasa campur (Indonesia + English technical terms)
    mixed_language = [
        {
            "topic": "Kecerdasan Buatan dan Machine Learning",
            "messages": [
                "Gradient descent itu optimization algorithm kan?",
                "Iya, buat minimize loss function",
                "Learning rate-nya harus di-tune carefully ya?",
            ],
            "should_intervene": False,
            "rationale": "Bahasa campur dengan terminologi teknis yang relevan dengan ML.",
        },
        {
            "topic": "Jaringan Komputer dan Protokol TCP/IP",
            "messages": [
                "Packet loss itu karena congestion kan?",
                "Iya, atau karena physical layer error",
                "Jadi perlu error detection mechanism?",
            ],
            "should_intervene": False,
            "rationale": "Diskusi teknis menggunakan terminologi networking yang tepat.",
        },
    ]

    for case in mixed_language:
        new_items.append(
            {
                "id": f"off_topic_{item_id:03d}",
                "intervention_type": "off_topic",
                "expected_should_intervene": case["should_intervene"],
                "input": {
                    "group_id": f"group_eval_{item_id:02d}",
                    "course_topic": case["topic"],
                    "recent_messages": case["messages"],
                    "message_count": len(case["messages"]),
                },
                "labeling_rationale": case["rationale"],
            }
        )
        item_id += 1

    # Combine with original dataset
    expanded_data = {
        "metadata": {
            "version": "2.0",
            "created": "2026-06-11",
            "total_items": len(base_data["items"]) + len(new_items),
            "description": "Expanded gold standard dataset with edge cases for Logic Listener evaluation.",
            "labeling_guidelines": base_data["metadata"]["labeling_guidelines"],
            "distribution": {
                "off_topic": {
                    "positive": 5
                    + len(
                        [
                            i
                            for i in new_items
                            if i["intervention_type"] == "off_topic"
                            and i["expected_should_intervene"]
                        ]
                    ),
                    "negative": 5
                    + len(
                        [
                            i
                            for i in new_items
                            if i["intervention_type"] == "off_topic"
                            and not i["expected_should_intervene"]
                        ]
                    ),
                },
                "silence": base_data["metadata"]["distribution"]["silence"],
                "participation_inequity": base_data["metadata"]["distribution"][
                    "participation_inequity"
                ],
            },
        },
        "items": base_data["items"] + new_items,
    }

    print(f"  Original items: {len(base_data['items'])}")
    print(f"  New synthetic items: {len(new_items)}")
    print(f"  Total items: {expanded_data['metadata']['total_items']}")
    print(f"  Saved to: {EXPANDED_DATASET_PATH}")

    with open(EXPANDED_DATASET_PATH, "w", encoding="utf-8") as f:
        json.dump(expanded_data, f, indent=2, ensure_ascii=False)

    return expanded_data


def evaluate_with_optimal(data: Dict, threshold: float) -> Dict:
    """Evaluate with optimal threshold on expanded dataset."""
    print("\n" + "=" * 72)
    print(f"  Final Evaluation — Threshold={threshold}, Expanded Dataset")
    print("=" * 72)

    listener = create_listener_with_real_embed(threshold)
    asyncio.run(listener.embedding_service.get_embedding("warmup"))

    # Off-topic
    off_tp, off_fp, off_fn = evaluate_off_topic(listener, data)
    off_p, off_r, off_f1 = compute_metrics(off_tp, off_fp, off_fn)

    print(f"\n  Off-topic Detection:")
    print(f"    TP={off_tp}, FP={off_fp}, FN={off_fn}")
    print(f"    Precision={off_p:.4f}, Recall={off_r:.4f}, F1={off_f1:.4f}")

    # Silence (deterministic)
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

    print(f"\n  Silence Detection:")
    print(f"    TP={sil_tp}, FP={sil_fp}, FN={sil_fn}")
    print(f"    Precision={sil_p:.4f}, Recall={sil_r:.4f}, F1={sil_f1:.4f}")

    # Participation inequity (deterministic)
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

    print(f"\n  Participation Inequity:")
    print(f"    TP={ineq_tp}, FP={ineq_fp}, FN={ineq_fn}")
    print(f"    Precision={ineq_p:.4f}, Recall={ineq_r:.4f}, F1={ineq_f1:.4f}")

    # Macro average
    macro_p = round((off_p + sil_p + ineq_p) / 3, 4)
    macro_r = round((off_r + sil_r + ineq_r) / 3, 4)
    macro_f1 = round((off_f1 + sil_f1 + ineq_f1) / 3, 4)

    print(f"\n  Macro Average:")
    print(f"    Precision={macro_p:.4f}, Recall={macro_r:.4f}, F1={macro_f1:.4f}")
    print("=" * 72)

    return {
        "threshold": threshold,
        "off_topic": {"precision": off_p, "recall": off_r, "f1": off_f1},
        "silence": {"precision": sil_p, "recall": sil_r, "f1": sil_f1},
        "participation_inequity": {
            "precision": ineq_p,
            "recall": ineq_r,
            "f1": ineq_f1,
        },
        "macro_average": {"precision": macro_p, "recall": macro_r, "f1": macro_f1},
    }


def main():
    print("Logic Listener Threshold Tuning & Dataset Expansion")
    print("=" * 72)

    # Load original dataset
    base_data = load_gold_standard()
    print(f"Loaded original dataset: {len(base_data['items'])} items")

    # Step 1: Tune threshold on original dataset
    tuning_results, best_threshold = tune_threshold(base_data)

    # Step 2: Generate expanded dataset
    expanded_data = generate_synthetic_dataset(base_data)

    # Step 3: Evaluate with optimal threshold on expanded dataset
    final_results = evaluate_with_optimal(expanded_data, best_threshold)

    # Summary
    print("\n" + "=" * 72)
    print("  SUMMARY")
    print("=" * 72)
    print(f"  Original dataset: 30 items")
    print(f"  Expanded dataset: {expanded_data['metadata']['total_items']} items")
    print(f"  Optimal threshold: {best_threshold}")
    print(f"  Off-topic F1: {final_results['off_topic']['f1']:.4f}")
    print(f"  Silence F1: {final_results['silence']['f1']:.4f}")
    print(f"  Participation F1: {final_results['participation_inequity']['f1']:.4f}")
    print(f"  Macro F1: {final_results['macro_average']['f1']:.4f}")
    print("=" * 72)

    # Save results
    results_path = (
        Path(__file__).parent.parent.parent
        / "data"
        / "evaluation"
        / "logic_listener_tuning_results.json"
    )
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "tuning": {str(k): v for k, v in tuning_results.items()},
                "optimal_threshold": best_threshold,
                "final_results": final_results,
            },
            f,
            indent=2,
        )
    print(f"\nResults saved to: {results_path}")


if __name__ == "__main__":
    main()
