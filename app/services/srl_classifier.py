import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class SRLPhase(str, Enum):
    FORETHOUGHT = "forethought"
    PERFORMANCE = "performance"
    REFLECTION = "reflection"


@dataclass
class SRLClassificationResult:
    phase: SRLPhase
    sub_phase: str
    confidence: float
    indicators: List[str]


class SRLClassifier:
    FORETHOUGHT_PATTERNS = {
        "goal_setting": [
            r"\b(tujuan|sasaran|target|goal|objective)\b",
            r"\b(ingin|mau|akan)\s+(memahami|mempelajari|menguasai|belajar|membuat)",
            r"\b(hari ini kita|kita akan|mari kita)\s+(bahas|diskusikan|pelajari)",
            r"\b(fokus|prioritas)\s+(kita|hari ini|saya)",
            r"\b(niat|berniat|bermaksud)\b",
        ],
        "planning": [
            r"\b(rencana|strategi|langkah|plan|berencana|merencanakan)\b",
            r"\b(pertama|kedua|ketiga|selanjutnya)\b.*\b(kita|akan)\b",
            r"\b(mari|ayo)\s+(mulai|kita mulai|kita bagi)",
            r"\b(pembagian|bagi)\s+(tugas|peran|topik)",
            r"\b(deadline|tenggat|batas waktu)\b",
            r"\b(jadwal|schedule|timeline)\b",
            r"\b(persiapan|mempersiapkan|menyiapkan)\b",
            r"\b(minggu ini|minggu depan|besok|nanti)\s+(akan|mau|saya)",
        ],
    }

    PERFORMANCE_PATTERNS = {
        "strategy_execution": [
            r"\b(menurut saya|saya pikir|saya rasa|pendapat saya)\b",
            r"\b(contoh|misalnya|seperti|analoginya)\b",
            r"\b(jadi|artinya|maksudnya|intinya)\b",
            r"\b(karena|sebab|alasannya|disebabkan)\b",
            r"\b(konsep|teori|definisi|pengertian)\b",
            r"\b(implementasi|penerapan|cara kerja)\b",
        ],
        "monitoring_control": [
            r"\b(apakah|sudahkah)\s+(kita|kalian)\b",
            r"\b(sejauh ini|sampai sini|progress)\b",
            r"\b(masih|belum)\s+(paham|mengerti|jelas)\b",
            r"\b(ada yang|siapa yang)\s+(mau|bisa)\s+(menjelaskan|membantu)",
            r"\b(tunggu|sebentar|wait)\b.*\b(cek|periksa|review)\b",
        ],
    }

    REFLECTION_PATTERNS = {
        "evaluation_reflection": [
            r"\b(kesimpulan|ringkasan|summary|intinya)\b",
            r"\b(setelah|dari)\s+(diskusi|pembahasan)\s+(tadi|ini|kita)\b",
            r"\b(sudah|telah)\s+(memahami|mengerti|paham)\b",
            r"\b(pelajaran|insight|hikmah)\s+(yang|dari)\b",
            r"\b(ternyata|rupanya|jadi begitu)\b",
        ],
        "metacognitive_adaptation": [
            r"\b(perlu|harus|sebaiknya)\s+(belajar|perbaiki|tingkatkan)\b",
            r"\b(lain kali|ke depan|next time)\b",
            r"\b(masih perlu|kurang|belum cukup)\b",
            r"\b(strategi|cara|metode)\s+(yang lebih|baru|berbeda)\b",
            r"\b(evaluasi|review|refleksi)\b",
        ],
    }

    PHASE_WEIGHTS = {
        SRLPhase.FORETHOUGHT: 1.2,
        SRLPhase.PERFORMANCE: 1.0,
        SRLPhase.REFLECTION: 1.3,
    }

    def classify(self, message: str) -> SRLClassificationResult:
        message_lower = message.lower()
        scores = {
            SRLPhase.FORETHOUGHT: {},
            SRLPhase.PERFORMANCE: {},
            SRLPhase.REFLECTION: {},
        }
        indicators = []

        for sub_phase, patterns in self.FORETHOUGHT_PATTERNS.items():
            count = 0
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    count += 1
                    indicators.append(f"forethought:{sub_phase}")
            scores[SRLPhase.FORETHOUGHT][sub_phase] = count

        for sub_phase, patterns in self.PERFORMANCE_PATTERNS.items():
            count = 0
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    count += 1
                    indicators.append(f"performance:{sub_phase}")
            scores[SRLPhase.PERFORMANCE][sub_phase] = count

        for sub_phase, patterns in self.REFLECTION_PATTERNS.items():
            count = 0
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    count += 1
                    indicators.append(f"reflection:{sub_phase}")
            scores[SRLPhase.REFLECTION][sub_phase] = count

        phase_totals = {}
        for phase, sub_scores in scores.items():
            phase_totals[phase] = sum(sub_scores.values()) * self.PHASE_WEIGHTS[phase]

        max_score = max(phase_totals.values())
        if max_score == 0:
            return SRLClassificationResult(
                phase=SRLPhase.PERFORMANCE,
                sub_phase="strategy_execution",
                confidence=0.3,
                indicators=[],
            )

        winning_phase = max(phase_totals, key=phase_totals.get)
        sub_scores = scores[winning_phase]
        winning_sub = max(sub_scores, key=sub_scores.get)
        total_all = sum(phase_totals.values())
        confidence = phase_totals[winning_phase] / total_all if total_all > 0 else 0.5

        return SRLClassificationResult(
            phase=winning_phase,
            sub_phase=winning_sub,
            confidence=min(confidence, 1.0),
            indicators=indicators,
        )


_srl_classifier: Optional[SRLClassifier] = None


def get_srl_classifier() -> SRLClassifier:
    global _srl_classifier
    if _srl_classifier is None:
        _srl_classifier = SRLClassifier()
    return _srl_classifier
