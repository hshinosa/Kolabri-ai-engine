"""
RAG Faithfulness Test
=====================

Mengukur proporsi klaim dalam jawaban yang didukung oleh konteks.
Target: > 0.85

Metode:
1. Extract klaim dari jawaban RAG
2. Verifikasi setiap klaim terhadap konteks retrieval
3. Hitung rasio klaim yang terverifikasi
"""

import asyncio
import json
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
import re


@dataclass
class FaithfulnessResult:
    total_claims: int
    supported_claims: int
    unsupported_claims: int
    score: float
    details: List[Dict[str, Any]]


class FaithfulnessEvaluator:
    """Evaluator untuk faithfulness RAG."""

    def __init__(self):
        self.min_score = 0.85  # Target

    def extract_claims(self, answer: str) -> List[str]:
        """Extract klaim-klaim dari jawaban."""
        # Split by . followed by space or end of string
        sentences = re.split(r"\.\s+", answer)
        claims = []
        for sent in sentences:
            sent = sent.strip()
            if sent.endswith("."):
                sent = sent[:-1]
            if len(sent) > 5:
                claims.append(sent)
        return claims

    def verify_claim_against_context(
        self, claim: str, contexts: List[str]
    ) -> Tuple[bool, str]:
        """Verifikasi satu klaim terhadap konteks."""
        claim_lower = claim.lower()
        for ctx in contexts:
            ctx_lower = ctx.lower()
            # Check if claim is a substring of context OR context is a substring of claim
            if claim_lower in ctx_lower or ctx_lower in claim_lower:
                return True, ctx
        return False, ""

    async def evaluate(self, answer: str, contexts: List[str]) -> FaithfulnessResult:
        """Evaluasi faithfulness jawaban RAG."""
        claims = self.extract_claims(answer)

        if not claims:
            return FaithfulnessResult(0, 0, 0, 1.0, [])

        supported = 0
        unsupported = 0
        details = []

        for claim in claims:
            is_supported = False
            evidence = ""
            claim_lower = claim.lower()
            for ctx in contexts:
                ctx_lower = ctx.lower()
                if claim_lower in ctx_lower:
                    is_supported = True
                    evidence = ctx
                    break

            if is_supported:
                supported += 1
            else:
                unsupported += 1

            details.append(
                {"claim": claim, "supported": is_supported, "evidence": evidence}
            )

        score = supported / len(claims) if len(claims) > 0 else 1.0
        return FaithfulnessResult(len(claims), supported, unsupported, score, details)

    def passed(self, result: FaithfulnessResult) -> bool:
        """Check jika score melewati target."""
        return result.score >= self.min_score


# Test cases
TEST_CASES = [
    {
        "name": "Basic ML Definition",
        "query": "Apa itu machine learning?",
        "contexts": [
            "Machine learning adalah cabang dari artificial intelligence yang memungkinkan sistem belajar dari data.",
            "ML menggunakan algoritma untuk mengidentifikasi pola dalam data dan membuat prediksi.",
        ],
        "expected_claims": ["machine learning", "AI", "algoritma", "data"],
    },
    {
        "name": "Neural Network Explanation",
        "query": "Jelaskan neural network",
        "contexts": [
            "Neural network terinspirasi dari cara kerja otak manusia.",
            "Neural network terdiri dari neuron buatan yang terhubung dalam layer.",
        ],
        "expected_claims": ["neural network", "otak", "neuron", "layer"],
    },
    {
        "name": "Comprehensive ML Concepts (5 contexts)",
        "query": "Jelaskan konsep machine learning secara lengkap",
        "contexts": [
            "Machine learning adalah metode analisis data yang mengotomatisasi pembangunan model analitik.",
            "Supervised learning menggunakan data berlabel untuk melatih model prediksi.",
            "Unsupervised learning menemukan pola tersembunyi dalam data tanpa label.",
            "Deep learning menggunakan neural network dengan banyak layer untuk pembelajaran kompleks.",
            "Model evaluation menggunakan metrik seperti accuracy, precision, dan recall untuk mengukur performa.",
        ],
        "expected_claims": [
            "supervised learning",
            "unsupervised learning",
            "deep learning",
            "accuracy",
        ],
    },
    {
        "name": "Database Systems (7 contexts)",
        "query": "Jelaskan sistem database relasional",
        "contexts": [
            "Database relasional menyimpan data dalam bentuk tabel dengan baris dan kolom.",
            "Primary key adalah kolom unik yang mengidentifikasi setiap baris dalam tabel.",
            "Foreign key menghubungkan tabel satu dengan tabel lain untuk menjaga integritas referensial.",
            "SQL (Structured Query Language) digunakan untuk query dan manipulasi data.",
            "Normalisasi adalah proses untuk mengurangi redundansi data dalam database.",
            "Index mempercepat pencarian data dengan membuat struktur data tambahan.",
            "Transaction memastikan operasi database berjalan dengan prinsip ACID (Atomicity, Consistency, Isolation, Durability).",
        ],
        "expected_claims": ["primary key", "foreign key", "SQL", "normalisasi", "ACID"],
    },
]


async def main():
    """Run faithfulness tests."""
    print("=" * 60)
    print("RAG FAITHFULNESS TEST")
    print("=" * 60)
    print(f"Target Score: > {FaithfulnessEvaluator().min_score}")
    print("=" * 60)

    evaluator = FaithfulnessEvaluator()

    for case in TEST_CASES:
        print(f"\nTest: {case['name']}")

        # Simulate RAG answer
        answer = " ".join(case["contexts"])

        result = await evaluator.evaluate(answer, case["contexts"])

        print(f"  Total Claims: {result.total_claims}")
        print(f"  Supported: {result.supported_claims}")
        print(f"  Unsupported: {result.unsupported_claims}")
        print(f"  Score: {result.score:.3f}")
        print(f"  Status: {'[PASS]' if evaluator.passed(result) else '[FAIL]'}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
