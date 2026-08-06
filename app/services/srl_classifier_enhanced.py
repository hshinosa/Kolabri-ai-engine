"""
Enhanced SRL Zimmerman Classifier - Production Ready
=====================================================
Production-ready improvements over baseline classifier:
1. Handles Indonesian word suffixes (-nya, -kan, -i)
2. Fuzzy matching for common variations
3. Confidence calibration with proper bounds
4. Scaffolding level recommendations per phase
5. Intervention routing hints
6. Better edge case handling
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class SRLPhase(str, Enum):
    FORETHOUGHT = "forethought"
    PERFORMANCE = "performance"
    REFLECTION = "reflection"


@dataclass
class EnhancedSRLClassificationResult:
    """Extended result with production features."""

    phase: SRLPhase
    sub_phase: str
    confidence: float
    indicators: List[str]

    # NEW: Enhancement fields for production use
    scaffolding_level: str  # "high", "medium", "low" based on phase
    intervention_hint: Optional[str]  # Suggested intervention type
    requires_attention: bool  # True if phase suggests intervention needed

    # Metadata for logging
    matched_patterns: List[str] = field(default_factory=list)
    pattern_scores: Dict[str, int] = field(default_factory=dict)


class EnhancedSRLClassifier:
    """
    Production-ready Zimmerman SRL classifier with enhancements.

    Key improvements:
    - Handles Indonesian suffixes: -(nya), -kan, -i
    - Flexible pattern matching for natural language
    - Phase-based scaffolding recommendations
    - Intervention routing hints
    - Robust confidence calibration
    """

    # Base patterns extended with suffix handling
    FORETHOUGHT_PATTERNS = {
        "goal_setting": [
            r"\b(tujuan|sasaran|target|goal|objective)\b",
            r"\b(ini\s+)?(tujuan|sasaran|target|goal|objective)-?\w*\b",
            r"\b(ingin|mau|akan)\s+(memahami|mempelajari|menguasai|belajar|membuat)\b",
            r"\b(mau|mencoba|berniat|bertujuan)\s+(untuk)?\s+\w+\s+(mempelajari|pahami)",
            r"\b(hari ini kita|kita akan|mari kita)\s+(bahas|diskusikan|pelajari)",
            r"\b(fokus|prioritas)\s+(kita|hari ini|saya)",
            r"\b(niat|berniat|bermaksud)\b",
            r"\b(target|goals|objective)-?\w*\b",
            r"\b(kita mau target(?:kan)? )",
        ],
        "planning": [
            r"\b(rencana|strategi|langkah|plan|berencana|merencanakan)\b",
            r"\b(pertama|kedua|ketiga|selanjutnya)\b.*\b(kita|akan)\b",
            r"\b(mari|ayo)\s+(mulai|kita mulai|kita bagi)\b",
            r"\b(pembagian|bagi)\s+(tugas|peran|topik)\b",
            r"\b(deadline|tenggat|batas waktu)\b",
            r"\b(jadwal|schedule|timeline)\b",
            r"\b(persiapan|mempersiapkan|menyiapkan)\b",
            r"\b(minggu ini|minggu depan|besok|nanti)\s+(akan|mau|saya)",
            r"\b(struktur|alur|urutan)\s+(langkah|tahapan|proses)\b",
            r"\b(bagi tugas|distribusi peran)",
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
            r"\b(algoritma|method|approach)",
            r"\b(dimulai dari|dilanjutkan dengan)",
        ],
        "monitoring_control": [
            r"\b(apakah|sudahkah)\s+(kita|kalian)\b",
            r"\b(sejauh ini|sampai sini|progress)\b",
            r"\b(masih|belum)\s+(paham|mengerti|jelas)\b",
            r"\b(ada yang|siapa yang)\s+(mau|bisa)\s+(menjelaskan|membantu)\b",
            r"\b(tunggu|sebentar|wait)\b.*\b(cek|periksa|review)\b",
            r"\b(apakah sudah|sudahkah sudah)",
            r"\b(coba cek|periksa dulu)",
        ],
    }

    REFLECTION_PATTERNS = {
        "evaluation_reflection": [
            r"\b(kesimpulan|ringkasan|summary|intinya|-?kesimpul)\b",
            r"\b(setelah|dari)\s+(diskusi|pembahasan|latihan|praktik)\s+(tadi|ini|kita)",
            r"\b(sudah|telah)\s+(memahami|mengerti|paham|-?pemahaman)\b",
            r"\b(pelajaran|insight|hikmah)\s+(yang|dari)\b",
            r"\b(ternyata|rupanya|jadi begitu)\b",
            r"\b(setelah praktik|setelah latihan)",
            r"\bbaru paham|baru ngerti",
        ],
        "metacognitive_adaptation": [
            r"\b(perlu|harus|sebaiknya)\s+(belajar|perbaiki|tingkatkan)\b",
            r"\b(lain kali|ke depan|next time)\b",
            r"\b(masih perlu|kurang|belum cukup)\b",
            r"\b(strategi|cara|metode)\s+(yang lebih|baru|berbeda)\b",
            r"\b(evaluasi|review|refleksi)\b",
            r"\b(perlu dipelajari lagi|lebih dalam lagi)",
            r"\b(learning point|takeaway)",
        ],
    }

    PHASE_WEIGHTS = {
        SRLPhase.FORETHOUGHT: 1.2,
        SRLPhase.PERFORMANCE: 1.0,
        SRLPhase.REFLECTION: 1.3,  # Highest weight for reflection (critical for learning)
    }

    # Scaffolding levels per phase
    SCAFFOLDING_LEVELS = {
        SRLPhase.FORETHOUGHT: "high",  # Need strong goal-setting support
        SRLPhase.PERFORMANCE: "medium",  # Moderate guidance needed
        SRLPhase.REFLECTION: "low",  # Mostly self-directed
    }

    # Intervention hints per phase
    INTERVENTION_HINTS = {
        SRLPhase.FORETHOUGHT: "Goal clarification & planning support",
        SRLPhase.PERFORMANCE: "Strategy validation & monitoring check-in",
        SRLPhase.REFLECTION: "Metacognitive reflection prompt",
    }

    def __init__(self):
        pass

    def classify(self, message: str) -> EnhancedSRLClassificationResult:
        """Classify message into Zimmerman phase with enhanced features."""

        if not message or not message.strip():
            return self._create_default_result()

        message_lower = message.lower()
        scores = {
            SRLPhase.FORETHOUGHT: {},
            SRLPhase.PERFORMANCE: {},
            SRLPhase.REFLECTION: {},
        }
        indicators = []
        matched_patterns = []

        # Classify each phase
        forethought_score = self._classify_phase(
            message_lower, self.FORETHOUGHT_PATTERNS, indicators, matched_patterns
        )
        performance_score = self._classify_phase(
            message_lower, self.PERFORMANCE_PATTERNS, indicators, matched_patterns
        )
        reflection_score = self._classify_phase(
            message_lower, self.REFLECTION_PATTERNS, indicators, matched_patterns
        )

        # Apply weights and calculate totals
        phase_totals = {
            SRLPhase.FORETHOUGHT: forethought_score
            * self.PHASE_WEIGHTS[SRLPhase.FORETHOUGHT],
            SRLPhase.PERFORMANCE: performance_score
            * self.PHASE_WEIGHTS[SRLPhase.PERFORMANCE],
            SRLPhase.REFLECTION: reflection_score
            * self.PHASE_WEIGHTS[SRLPhase.REFLECTION],
        }

        max_score = max(phase_totals.values())

        if max_score == 0:
            return self._create_default_result(
                indicators=indicators, matched_patterns=matched_patterns
            )

        # Determine winning phase
        winning_phase = max(phase_totals, key=phase_totals.get)

        # Get sub-phase details
        phase_indicators = [
            ind for ind in indicators if ind.startswith(winning_phase.value + ":")
        ]
        winning_sub = (
            phase_indicators[0].split(":")[1] if phase_indicators else "unknown"
        )

        # Calculate calibrated confidence
        total_all = sum(phase_totals.values())
        raw_confidence = phase_totals[winning_phase] / total_all

        # Confidence calibration: clamp to [0.3, 0.95] range
        calibrated_confidence = max(0.3, min(0.95, raw_confidence))

        # Determine scaffolding level and intervention hint
        scaffolding_level = self.SCAFFOLDING_LEVELS[winning_phase]
        intervention_hint = self.INTERVENTION_HINTS[winning_phase]

        # Requires attention flag (true for reflection = metacognitive awareness)
        requires_attention = winning_phase == SRLPhase.REFLECTION

        return EnhancedSRLClassificationResult(
            phase=winning_phase,
            sub_phase=winning_sub,
            confidence=calibrated_confidence,
            indicators=indicators,
            scaffolding_level=scaffolding_level,
            intervention_hint=intervention_hint,
            requires_attention=requires_attention,
            matched_patterns=matched_patterns[:10],  # Limit to top 10 matches
            pattern_scores={
                SRLPhase.FORETHOUGHT.value: forethought_score,
                SRLPhase.PERFORMANCE.value: performance_score,
                SRLPhase.REFLECTION.value: reflection_score,
            },
        )

    def _classify_phase(
        self,
        message: str,
        patterns: Dict[str, List[str]],
        indicators: List[str],
        matched_patterns: List[str],
    ) -> float:
        """Classify a single phase and return weighted score."""
        total_score = 0.0

        for sub_phase, pattern_list in patterns.items():
            count = 0
            for pattern in pattern_list:
                try:
                    if re.search(pattern, message):
                        count += 1
                        indicator = f"{list(patterns.keys())[0]}:{sub_phase}"
                        if indicator not in indicators:
                            indicators.append(indicator)

                        # Track matched patterns for debugging
                        matched_patterns.append(pattern)
                except re.error as e:
                    logger.warning(f"Invalid regex pattern: {pattern}, error: {e}")

            if count > 0:
                total_score += count * 1.5  # Weight multiple matches

        return total_score

    def _create_default_result(
        self, indicators: List[str] = None, matched_patterns: List[str] = None
    ) -> EnhancedSRLClassificationResult:
        """Create default result when no patterns match."""
        return EnhancedSRLClassificationResult(
            phase=SRLPhase.PERFORMANCE,
            sub_phase="strategy_execution",
            confidence=0.3,
            indicators=indicators or [],
            scaffolding_level="medium",
            intervention_hint=None,
            requires_attention=False,
            matched_patterns=matched_patterns or [],
            pattern_scores={},
        )

    def get_recommendations(
        self, result: EnhancedSRLClassificationResult
    ) -> Dict[str, Any]:
        """Generate actionable recommendations based on classification."""

        recommendations = {
            "scaffolding_action": self._get_scaffolding_action(result.phase),
            "intervention_type": self._suggest_intervention(result.phase),
            "follow_up_needed": result.requires_attention,
            "priority_level": self._calculate_priority(result.confidence, result.phase),
        }

        return recommendations

    def _get_scaffolding_action(self, phase: SRLPhase) -> str:
        """Get recommended scaffolding action per phase."""
        actions = {
            SRLPhase.FORETHOUGHT: "Guide goal-setting, provide planning templates",
            SRLPhase.PERFORMANCE: "Monitor progress, validate strategies, offer examples",
            SRLPhase.REFLECTION: "Prompt metacognitive questions, encourage self-assessment",
        }
        return actions.get(phase, "Provide standard support")

    def _suggest_intervention(self, phase: SRLPhase) -> str:
        """Suggest intervention type based on phase."""
        interventions = {
            SRLPhase.FORETHOUGHT: "GOAL_CLARIFICATION",
            SRLPhase.PERFORMANCE: "STRATEGY_VALIDATION",
            SRLPhase.REFLECTION: "METACOGNITIVE_PROMPT",
        }
        return interventions.get(phase, "MONITOR_ONLY")

    def _calculate_priority(self, confidence: float, phase: SRLPhase) -> str:
        """Calculate priority level based on confidence and phase."""
        if confidence < 0.4:
            return "LOW"
        elif confidence > 0.7 and phase == SRLPhase.REFLECTION:
            return "HIGH"
        else:
            return "MEDIUM"


# Singleton instance
_clf_instance: Optional[EnhancedSRLClassifier] = None


def get_enhanced_srl_classifier() -> EnhancedSRLClassifier:
    """Get singleton instance of enhanced classifier."""
    global _clf_instance
    if _clf_instance is None:
        _clf_instance = EnhancedSRLClassifier()
    return _clf_instance


# Keep backward compatibility alias
get_srl_classifier = get_enhanced_srl_classifier
