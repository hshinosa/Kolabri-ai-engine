"""
Output Grounding Verification Service
======================================
Implements TA Algorithm 1 OutputGuardrails(R, D):
- Extract claims from LLM response
- Verify each claim is grounded in retrieved documents
- Block response if grounding ratio < threshold

Reference: Bab 2 §2.4, Lewis et al. (2020)
"""

import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import numpy as np

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GroundingResult:
    is_grounded: bool
    grounding_ratio: float
    confidence: float
    ungrounded_claims: List[str]
    grounded_claims: List[str]
    total_claims: int


class GroundingVerifier:
    """
    Verifies LLM output is grounded in retrieved documents.

    Implements OutputGuardrails from TA Algorithm 1:
    1. Extract claims (sentence-level)
    2. Check semantic similarity against documents
    3. Block if grounding_ratio < threshold
    """

    DEFAULT_CLAIM_THRESHOLD = 0.15
    DEFAULT_OVERALL_THRESHOLD = 0.1

    NON_FACTUAL_PATTERNS = [
        r"^(maaf|sorry|saya tidak)",
        r"\?$",
        r"^(mungkin|barangkali|sepertinya)",
        r"^(silakan|coba|cobalah)",
        r"^(pertanyaan socratic|pertanyaan lanjutan)",
        r"^(menurut kamu|menurut kalian)",
        r"^(ya,?\s+pertanyaan)",
        r"^\d+\.\s*\*\*",
    ]

    def __init__(self, embedding_service=None):
        self._embedding_service = embedding_service

    @property
    def embedding_service(self):
        if self._embedding_service is None:
            from app.services.embeddings import get_embedding_service

            self._embedding_service = get_embedding_service()
        return self._embedding_service

    def _extract_claims(self, response: str) -> List[str]:
        cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", response)
        cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
        cleaned = re.sub(r"📚.*$", "", cleaned, flags=re.MULTILINE | re.DOTALL)
        cleaned = re.sub(r"^[-•]\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"^\d+\.\s*", "", cleaned, flags=re.MULTILINE)

        sentences = re.split(r"[.!?]\s+|\n\n+", cleaned.strip())
        sentences = [s.strip() for s in sentences if len(s.strip()) > 15]

        claims = []
        for sentence in sentences:
            is_factual = True
            for pattern in self.NON_FACTUAL_PATTERNS:
                if re.search(pattern, sentence.lower()):
                    is_factual = False
                    break
            if is_factual:
                claims.append(sentence)

        return claims if claims else sentences[:1]

    def _compute_similarity(self, text_a: str, text_b: str) -> float:
        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())

        if not words_a or not words_b:
            return 0.0

        intersection = words_a & words_b
        union = words_a | words_b

        return len(intersection) / len(union) if union else 0.0

    async def _compute_similarity_async(self, text_a: str, text_b: str) -> float:
        # PERF-AI-05: Cache embeddings to avoid redundant calls
        try:
            vec_a = await self._get_cached_embedding(text_a)
            vec_b = await self._get_cached_embedding(text_b)

            similarity = np.dot(vec_a, vec_b) / (
                np.linalg.norm(vec_a) * np.linalg.norm(vec_b)
            )
            return float(similarity)
        except Exception as e:
            logger.warning("embedding_similarity_failed", error=str(e))
            return self._compute_similarity(text_a, text_b)

    async def _get_cached_embedding(self, text: str):
        """Get embedding with in-memory cache to avoid redundant calls."""
        if not hasattr(self, '_embedding_cache'):
            self._embedding_cache = {}
        if text not in self._embedding_cache:
            self._embedding_cache[text] = await self.embedding_service.get_embedding(text)
        return self._embedding_cache[text]

    def verify_grounding(
        self,
        response: str,
        documents: List[Dict[str, Any]],
        threshold: float = None,
        claim_threshold: float = None,
    ) -> GroundingResult:
        overall_threshold = threshold or self.DEFAULT_OVERALL_THRESHOLD
        per_claim_threshold = claim_threshold or self.DEFAULT_CLAIM_THRESHOLD

        if not documents:
            return GroundingResult(
                is_grounded=False,
                grounding_ratio=0.0,
                confidence=1.0,
                ungrounded_claims=[response[:100]],
                grounded_claims=[],
                total_claims=1,
            )

        claims = self._extract_claims(response)

        if not claims:
            return GroundingResult(
                is_grounded=True,
                grounding_ratio=1.0,
                confidence=0.5,
                ungrounded_claims=[],
                grounded_claims=[],
                total_claims=0,
            )

        doc_contents = [
            doc.get("content", doc.get("page_content", "")) for doc in documents
        ]
        all_context = " ".join(doc_contents)

        grounded_claims = []
        ungrounded_claims = []

        for claim in claims:
            max_similarity = 0.0
            for doc_content in doc_contents:
                sim = self._compute_similarity(claim, doc_content)
                max_similarity = max(max_similarity, sim)

            overall_sim = self._compute_similarity(claim, all_context)
            max_similarity = max(max_similarity, overall_sim)

            if max_similarity >= per_claim_threshold:
                grounded_claims.append(claim)
            else:
                ungrounded_claims.append(claim)

        grounding_ratio = len(grounded_claims) / len(claims) if claims else 1.0
        is_grounded = grounding_ratio >= overall_threshold

        confidence = abs(grounding_ratio - overall_threshold) / overall_threshold
        confidence = min(confidence + 0.5, 1.0)

        logger.info(
            "grounding_verification_complete",
            is_grounded=is_grounded,
            ratio=round(grounding_ratio, 3),
            total_claims=len(claims),
            grounded=len(grounded_claims),
            ungrounded=len(ungrounded_claims),
        )

        return GroundingResult(
            is_grounded=is_grounded,
            grounding_ratio=grounding_ratio,
            confidence=confidence,
            ungrounded_claims=ungrounded_claims,
            grounded_claims=grounded_claims,
            total_claims=len(claims),
        )

    async def verify_grounding_async(
        self,
        response: str,
        documents: List[Dict[str, Any]],
        threshold: float = None,
        claim_threshold: float = None,
    ) -> GroundingResult:
        overall_threshold = threshold or self.DEFAULT_OVERALL_THRESHOLD
        per_claim_threshold = claim_threshold or self.DEFAULT_CLAIM_THRESHOLD

        if not documents:
            return GroundingResult(
                is_grounded=False,
                grounding_ratio=0.0,
                confidence=1.0,
                ungrounded_claims=[response[:100]],
                grounded_claims=[],
                total_claims=1,
            )

        claims = self._extract_claims(response)
        if not claims:
            return GroundingResult(
                is_grounded=True,
                grounding_ratio=1.0,
                confidence=0.5,
                ungrounded_claims=[],
                grounded_claims=[],
                total_claims=0,
            )

        doc_contents = [
            doc.get("content", doc.get("page_content", "")) for doc in documents
        ]
        all_context = " ".join(doc_contents)

        grounded_claims = []
        ungrounded_claims = []

        for claim in claims:
            embedding_sim = 0.0
            for doc_content in doc_contents:
                sim = await self._compute_similarity_async(claim, doc_content)
                embedding_sim = max(embedding_sim, sim)

            keyword_sim = self._compute_similarity(claim, all_context)

            hybrid_score = 0.7 * embedding_sim + 0.3 * keyword_sim

            if hybrid_score >= per_claim_threshold:
                grounded_claims.append(claim)
            else:
                ungrounded_claims.append(claim)
        grounding_ratio = len(grounded_claims) / len(claims)
        is_grounded = grounding_ratio >= overall_threshold

        confidence = min(
            abs(grounding_ratio - overall_threshold) / max(overall_threshold, 0.01)
            + 0.5,
            1.0,
        )

        logger.info(
            "grounding_verification_complete",
            is_grounded=is_grounded,
            ratio=round(grounding_ratio, 3),
            total_claims=len(claims),
            grounded=len(grounded_claims),
            ungrounded=len(ungrounded_claims),
        )

        return GroundingResult(
            is_grounded=is_grounded,
            grounding_ratio=grounding_ratio,
            confidence=confidence,
            ungrounded_claims=ungrounded_claims,
            grounded_claims=grounded_claims,
            total_claims=len(claims),
        )


_grounding_verifier: Optional[GroundingVerifier] = None


def get_grounding_verifier() -> GroundingVerifier:
    global _grounding_verifier
    if _grounding_verifier is None:
        _grounding_verifier = GroundingVerifier()
    return _grounding_verifier
