import random
import re
from dataclasses import dataclass
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SocraticResult:
    is_direct_answer: bool
    confidence: float
    scaffolded_response: Optional[str]
    reason: str


class SocraticFilter:
    SCAFFOLDING_INDICATORS = [
        r"\?",
        r"\b(coba|cobalah)\s+(pikirkan|bayangkan|pertimbangkan)",
        r"\b(menurutmu|menurut kamu|bagaimana pendapatmu)",
        r"\b(apa yang terjadi jika|bagaimana jika)",
        r"\b(bisakah kamu|dapatkah kamu)",
        r"\b(pertama|langkah pertama)",
        r"\b(hint|petunjuk|clue)",
        r"\b(think about|consider|what if|how would you)",
        r"\b(can you|try to|let\'s think)",
    ]

    DIRECT_ANSWER_INDICATORS = [
        r"\b(adalah|merupakan|yaitu|ialah)\b.*\.",
        r"\b(jawabannya|hasilnya|outputnya)\s+(adalah|=)",
        r"\b(the answer is|the result is)",
        r"^\d+\.\s+\w+",
        r"\b(langkah-langkah|steps):\s*\n",
    ]

    EXEMPT_PATTERNS = [
        r"^(halo|hai|hi|hello|selamat)",
        r"^(terima kasih|thanks|ok|oke)",
    ]

    SOCRATIC_TEMPLATES = [
        "Pertanyaan yang menarik! Mari kita telusuri bersama:\n\n1. {hint_1}\n2. {hint_2}\n\nCoba pikirkan hubungan antara kedua hal tersebut. Apa kesimpulanmu?",
        "Bagus, mari kita pecahkan ini langkah demi langkah:\n\nPertama, {hint_1}\nKedua, {hint_2}\n\nDari situ, menurutmu apa yang bisa kita simpulkan?",
        "Sebelum saya jelaskan langsung, coba pikirkan:\n\n- {hint_1}\n- {hint_2}\n\nBagaimana menurutmu? Apakah kamu bisa melihat polanya?",
    ]

    MIN_CHECK_LENGTH = 50

    def _is_exempt_query(self, query: str) -> bool:
        query_lower = query.lower().strip()
        return any(re.search(pattern, query_lower) for pattern in self.EXEMPT_PATTERNS)

    def _has_scaffolding(self, response: str) -> bool:
        return any(re.search(pattern, response, re.IGNORECASE) for pattern in self.SCAFFOLDING_INDICATORS)

    def _is_direct_answer(self, response: str) -> float:
        score = 0.0
        checks = 0

        for pattern in self.DIRECT_ANSWER_INDICATORS:
            checks += 1
            if re.search(pattern, response, re.IGNORECASE | re.MULTILINE):
                score += 1.0

        question_count = response.count("?")
        sentence_count = max(len(re.split(r"[.!?]", response)), 1)
        question_ratio = question_count / sentence_count

        checks += 1
        if question_ratio < 0.1:
            score += 1.0

        checks += 1
        if len(response) > 200 and question_count == 0:
            score += 1.0

        return score / checks if checks else 0.0

    def _generate_scaffolded_response(self, query: str, original_response: str) -> str:
        sentences = re.split(r"[.!?]\s+", original_response)
        hints = [s.strip() for s in sentences if len(s.strip()) > 15][:2]

        if len(hints) < 2:
            hints = [
                f"Pikirkan tentang konsep dasar yang terkait dengan '{query[:30]}'",
                "Bagaimana konsep ini berhubungan dengan apa yang sudah kamu pelajari sebelumnya?",
            ]

        template = random.choice(self.SOCRATIC_TEMPLATES)
        return template.format(
            hint_1=hints[0],
            hint_2=hints[1] if len(hints) > 1 else "Bagaimana ini berhubungan dengan konsep sebelumnya?",
        )

    def check_response(self, query: str, response: str) -> SocraticResult:
        if len(response) < self.MIN_CHECK_LENGTH or self._is_exempt_query(query):
            return SocraticResult(False, 1.0, None, "exempt_query_or_short_response")

        if self._has_scaffolding(response):
            return SocraticResult(False, 0.9, None, "already_scaffolded")

        directness_score = self._is_direct_answer(response)

        if directness_score >= 0.25:
            scaffolded = self._generate_scaffolded_response(query, response)
            logger.info("direct_answer_detected", query=query[:50], directness_score=round(directness_score, 3))
            return SocraticResult(True, directness_score, scaffolded, "direct_answer_without_scaffolding")

        return SocraticResult(False, 1.0 - directness_score, None, "acceptable_response")


_socratic_filter: Optional[SocraticFilter] = None


def get_socratic_filter() -> SocraticFilter:
    global _socratic_filter
    if _socratic_filter is None:
        _socratic_filter = SocraticFilter()
    return _socratic_filter
