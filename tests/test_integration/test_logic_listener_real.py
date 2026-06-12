"""
Real System Integration Test for Logic Listener
================================================

Uses actual FastEmbed model instead of mock embeddings.
This test validates Logic Listener behavior with real vector representations.

IMPORTANT: This file must NOT import fastembed or numpy at module level
because conftest.py mocks them globally. Real modules are imported dynamically
inside fixtures/tests.

Run:
    pytest tests/test_integration/test_logic_listener_real.py -v -s --tb=short

Or with markers:
    pytest -m "integration and not slow" tests/test_integration/test_logic_listener_real.py -v
"""

import sys
import json
import time
import asyncio
import math
from pathlib import Path
from typing import Dict, List, Tuple, Any
from unittest.mock import MagicMock, patch

import pytest

# Import LogicListener using mocked modules (conftest.py handles mocks)
from app.services.logic_listener import LogicListener, InterventionType

DATASET_PATH = (
    Path(__file__).parent.parent.parent
    / "data"
    / "evaluation"
    / "logic_listener_gold_standard.json"
)


# =============================================================================
# HELPERS
# =============================================================================


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


def _cosine_sim(vec1: List[float], vec2: List[float]) -> float:
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 * norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


# =============================================================================
# REAL EMBEDDING SERVICE (dynamically imports real modules)
# =============================================================================


class RealEmbeddingService:
    """Real embedding service using FastEmbed model (local, no API key).

    Dynamically imports fastembed to avoid conftest.py mock conflicts.
    """

    def __init__(self):
        # Dynamically import real fastembed module
        import importlib

        # Remove mock if present
        if "fastembed" in sys.modules:
            del sys.modules["fastembed"]
        if "numpy" in sys.modules:
            del sys.modules["numpy"]

        try:
            fastembed = importlib.import_module("fastembed")
            self._TextEmbedding = fastembed.TextEmbedding
            self._model = self._TextEmbedding(
                model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            )
        except ImportError as e:
            raise RuntimeError(f"Failed to import real fastembed: {e}")

    async def get_embedding(self, text: str) -> List[float]:
        embeddings = list(self._model.embed([text]))
        return embeddings[0].tolist()

    async def embed_text(self, text: str) -> List[float]:
        return await self.get_embedding(text)

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        embeddings = list(self._model.embed(texts))
        return [e.tolist() for e in embeddings]


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(scope="session")
def real_embedding_service():
    """Session-scoped fixture for real embedding service with lazy init."""
    try:
        service = RealEmbeddingService()
        # Warm up with a dummy embedding to trigger model download/load
        asyncio.run(service.get_embedding("warmup"))
        yield service
    except RuntimeError as e:
        pytest.skip(f"Real embedding service unavailable: {e}")


@pytest.fixture
def real_logic_listener(real_embedding_service):
    """Create LogicListener with real embedding service injected."""
    with (
        patch(
            "app.services.logic_listener.get_embedding_service",
            return_value=real_embedding_service,
        ),
        patch("app.services.logic_listener.get_mongo_logger", return_value=MagicMock()),
    ):
        listener = LogicListener()
        return listener


# =============================================================================
# TESTS
# =============================================================================


@pytest.mark.integration
@pytest.mark.slow
class TestLogicListenerRealSystem:
    """Integration tests using real FastEmbed model and gold standard dataset."""

    def test_dataset_loads(self):
        """Verify gold standard dataset loads correctly."""
        data = load_gold_standard()
        assert data["metadata"]["total_items"] == 30
        assert len(data["items"]) == 30

        for itype in ("off_topic", "silence", "participation_inequity"):
            typed = [i for i in data["items"] if i["intervention_type"] == itype]
            assert len(typed) == 10
            assert len([i for i in typed if i["expected_should_intervene"]]) == 5
            assert len([i for i in typed if not i["expected_should_intervene"]]) == 5

    def test_real_embedding_service_available(self, real_embedding_service):
        """Verify real embedding service produces valid embeddings."""
        embedding = asyncio.run(real_embedding_service.get_embedding("test"))
        assert len(embedding) > 0
        assert all(isinstance(x, float) for x in embedding)

        # Verify semantic similarity works roughly as expected
        emb1 = asyncio.run(real_embedding_service.get_embedding("machine learning"))
        emb2 = asyncio.run(real_embedding_service.get_embedding("deep learning"))
        emb3 = asyncio.run(real_embedding_service.get_embedding("makan nasi goreng"))

        sim_12 = _cosine_sim(emb1, emb2)
        sim_13 = _cosine_sim(emb1, emb3)

        # ML and DL should be more similar than ML and food
        assert sim_12 > sim_13, (
            f"Semantic similarity failed: ML-DL={sim_12:.3f} vs ML-food={sim_13:.3f}"
        )

    def test_off_topic_with_real_embeddings(self, real_logic_listener):
        """Test off-topic detection with real FastEmbed embeddings."""
        data = load_gold_standard()
        items = [i for i in data["items"] if i["intervention_type"] == "off_topic"]

        tp = fp = fn = 0
        for item in items:
            inp = item["input"]
            group_id = inp["group_id"]
            expected = item["expected_should_intervene"]

            # Set group topic
            asyncio.run(
                real_logic_listener.set_group_topic(group_id, inp["course_topic"])
            )

            # Process all messages in sequence
            result = None
            for msg in inp["recent_messages"]:
                result = asyncio.run(real_logic_listener.check_relevance(msg, group_id))

            predicted = result.should_intervene if result else False

            if predicted and expected:
                tp += 1
            elif predicted and not expected:
                fp += 1
            elif not predicted and expected:
                fn += 1

        precision, recall, f1 = compute_metrics(tp, fp, fn)
        print(
            f"\n[REAL OFF-TOPIC] TP={tp} FP={fp} FN={fn} "
            f"→ P={precision} R={recall} F1={f1}"
        )

        # Real embedding may not be perfect; assert reasonable minimum
        assert f1 >= 0.5, f"Real off-topic F1 too low: {f1}"
        assert precision >= 0.4, f"Real off-topic precision too low: {precision}"
        assert recall >= 0.4, f"Real off-topic recall too low: {recall}"

    def test_silence_with_real_system(self, real_logic_listener):
        """Test silence detection (deterministic, should be perfect)."""
        data = load_gold_standard()
        items = [i for i in data["items"] if i["intervention_type"] == "silence"]

        tp = fp = fn = 0
        for item in items:
            inp = item["input"]
            group_id = inp["group_id"]
            expected = item["expected_should_intervene"]

            # Inject timestamp directly to bypass async track_message
            real_logic_listener._last_message_timestamp[group_id] = (
                time.time() - inp["last_message_seconds_ago"]
            )

            predicted = real_logic_listener.check_silence(group_id).should_intervene

            if predicted and expected:
                tp += 1
            elif predicted and not expected:
                fp += 1
            elif not predicted and expected:
                fn += 1

        precision, recall, f1 = compute_metrics(tp, fp, fn)
        print(
            f"\n[REAL SILENCE] TP={tp} FP={fp} FN={fn} "
            f"→ P={precision} R={recall} F1={f1}"
        )

        # Silence is purely deterministic (time threshold)
        assert f1 == 1.0, f"Silence F1 should be 1.0, got {f1}"
        assert precision == 1.0
        assert recall == 1.0

    def test_participation_inequity_with_real_system(self, real_logic_listener):
        """Test participation inequity (deterministic, should be perfect)."""
        data = load_gold_standard()
        items = [
            i
            for i in data["items"]
            if i["intervention_type"] == "participation_inequity"
        ]

        tp = fp = fn = 0
        for item in items:
            inp = item["input"]
            group_id = inp["group_id"]
            expected = item["expected_should_intervene"]

            # Inject counts directly to bypass async track_participation
            real_logic_listener._participation_counts[group_id] = dict(
                inp["message_counts_per_user"]
            )

            predicted = real_logic_listener.check_participation_inequity(
                group_id
            ).should_intervene

            if predicted and expected:
                tp += 1
            elif predicted and not expected:
                fp += 1
            elif not predicted and expected:
                fn += 1

        precision, recall, f1 = compute_metrics(tp, fp, fn)
        print(
            f"\n[REAL INEQUITY] TP={tp} FP={fp} FN={fn} "
            f"→ P={precision} R={recall} F1={f1}"
        )

        # Participation inequity is purely deterministic (Gini threshold)
        assert f1 == 1.0, f"Participation inequity F1 should be 1.0, got {f1}"
        assert precision == 1.0
        assert recall == 1.0

    def test_full_evaluation_report(self, real_logic_listener):
        """Generate full evaluation report with real embeddings."""
        data = load_gold_standard()

        # Evaluate all three intervention types
        off_tp, off_fp, off_fn = self._evaluate_off_topic(real_logic_listener, data)
        sil_tp, sil_fp, sil_fn = self._evaluate_silence(real_logic_listener, data)
        ineq_tp, ineq_fp, ineq_fn = self._evaluate_participation_inequity(
            real_logic_listener, data
        )

        off_p, off_r, off_f1 = compute_metrics(off_tp, off_fp, off_fn)
        sil_p, sil_r, sil_f1 = compute_metrics(sil_tp, sil_fp, sil_fn)
        ineq_p, ineq_r, ineq_f1 = compute_metrics(ineq_tp, ineq_fp, ineq_fn)

        macro_p = round((off_p + sil_p + ineq_p) / 3, 4)
        macro_r = round((off_r + sil_r + ineq_r) / 3, 4)
        macro_f1 = round((off_f1 + sil_f1 + ineq_f1) / 3, 4)

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
        print(
            f"  {'Macro Average':<30} {macro_p:>9.4f} {macro_r:>8.4f} {macro_f1:>8.4f}"
        )
        print("=" * 72 + "\n")

        # Assert minimum quality thresholds
        assert macro_f1 >= 0.7, f"Macro F1 too low: {macro_f1}"
        assert off_f1 >= 0.5, f"Off-topic F1 too low: {off_f1}"
        assert sil_f1 == 1.0
        assert ineq_f1 == 1.0

    # -------------------------------------------------------------------------
    # Helper methods
    # -------------------------------------------------------------------------

    def _evaluate_off_topic(
        self, listener: LogicListener, data: Dict
    ) -> Tuple[int, int, int]:
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

    def _evaluate_silence(
        self, listener: LogicListener, data: Dict
    ) -> Tuple[int, int, int]:
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

    def _evaluate_participation_inequity(
        self, listener: LogicListener, data: Dict
    ) -> Tuple[int, int, int]:
        items = [
            i
            for i in data["items"]
            if i["intervention_type"] == "participation_inequity"
        ]
        tp = fp = fn = 0
        for item in items:
            inp = item["input"]
            group_id = inp["group_id"]
            expected = item["expected_should_intervene"]

            listener._participation_counts[group_id] = dict(
                inp["message_counts_per_user"]
            )
            predicted = listener.check_participation_inequity(group_id).should_intervene

            if predicted and expected:
                tp += 1
            elif predicted and not expected:
                fp += 1
            elif not predicted and expected:
                fn += 1

        return tp, fp, fn
