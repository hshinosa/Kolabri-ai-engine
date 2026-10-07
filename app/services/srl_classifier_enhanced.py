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
            r"\b(topik|bahasan|materi)\s+(kita|hari ini|minggu ini)\b",
            r"\b(kita|kami|aku|saya)\s+(akan|mau|ingin|perlu|harus)\s+(membahas|membaca|mempelajari|mengerjakan|mencoba|menganalisis|menguji|membuat|mendesain)\b",
            r"\b(niatku|tujuan aku|tujuan kita|yang mau (kita|aku) capai|capaian kita)\b",
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
            r"\b(rencana|strategi|langkah|target|tujuan|sasaran|jadwal|tenggat|deadline|prioritas|persiapan|timeline|schedule|plan)\w*\b",
            r"\b(yang pertama|pertama-tama|langkah pertama|tahap awal|sebelum (kita )?(mulai|memulai|bahas|diskusi))\b",
            r"\bkita (mulai|buka|bahas|kerjakan|kerjain|bagi|putar)\b",
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
            r"\b(berdasarkan|dari|sesuai)\s+(analisis|evaluasi|pengalaman|observasi|hasil)\b",
            r"\b(aku|saya|menurutku|menurut aku|gue)\s+(menganalisis|membandingkan|mengusulkan|menemukan|menguji|mendesain|merancang|memilih)\b",
            r"\b(kelebihan|kekurangan|trade-?offs?|limitasi)\b",
            r"\b(lebih (efisien|cepat|baik|robust|tepat|aman|stabil|hemat|murah))\b",
            r"\b(sehingga|makanya|oleh karena itu|dengan begitu)\b",
            r"\b(menurutku|menurut aku|kalau menurutku|kayaknya|sepertinya)\b",
            r"\b(kasus terburuk\w*|kasus terbaik\w*|rata-rata|di sisi lain)\b",
        ],
        "monitoring_control": [
            r"\b(apakah|sudahkah)\s+(kita|kalian)\b",
            r"\b(sejauh ini|sampai sini|progress)\b",
            r"\b(masih|belum)\s+(paham|mengerti|jelas)\b",
            r"\b(ada yang|siapa yang)\s+(mau|bisa)\s+(menjelaskan|membantu)\b",
            r"\b(tunggu|sebentar|wait)\b.*\b(cek|periksa|review)\b",
            r"\b(apakah sudah|sudahkah sudah)",
            r"\b(coba cek|periksa dulu)",
            r"\b(gimana|bagaimana|kenapa|mengapa|berapa|dimana|kapan|apa|apakah|bisakah|dapatkah)\b[^\n]{0,60}\?",
            r"\b(apa|kenapa|gimana|bagaimana)\s+(sih|dong|ya|gak|nggak|enggak|kok)\b",
            r"\b(bingung|pusing|keder|ragu)\w*\b",
            r"\b(belum|masih belum|aku belum|saya belum)\s+(paham|ngerti|mengerti|jelas|tau|tahu)\b",
            r"\b(ada yang|ada siapa|siapa yang|mana yang)\s+(bisa|mau|tahu|tau)\b",
            r"\b(jelaskan|jelasin|terangkan|uraikan|tolong jelaskan|bantu jelaskan)\w*\b",
            r"\b(susah|ribet|rumit|kompleks|deg-degan|cemas|khawatir|berat)\w*\b",
            r"\b(udah|sudah)\s+\w*\s*(ngerjain|negerjain|selesai|beres|kumpul)\w*\b",
        ],
    }

    REFLECTION_PATTERNS = {
        "evaluation_reflection": [
            r"\b(-?kesimpul\w*|ringkasan\w*|summary|intinya)\b",
            r"\b(setelah|dari)\s+(diskusi|pembahasan|latihan|praktik)\s+(tadi|ini|kita)",
            r"\b(sudah|telah)\s+(memahami|mengerti|paham|-?pemahaman)\b",
            r"\b(pelajaran|insight|hikmah)\s+(yang|dari)\b",
            r"\b(ternyata|rupanya|jadi begitu)\b",
            r"\b(setelah praktik|setelah latihan)",
            r"\bbaru paham|baru ngerti",
            r"\b(menyimpulkan|disimpulkan|simpulkan|ringkasan\w*|rekapitulasi)\b",
            r"\b(akhirnya (paham|ngerti|tau|mengerti)|selesai sudah|setelah semua selesai)\b",
            r"\b(yang aku (kira|pikir|duga)[^.!?]{0,40}(ternyata|nyatanya|rupanya))\b",
            r"\b(pelajaran hari ini|yang sudah aku pelajari|hasil belajar)\b",
        ],
        "metacognitive_adaptation": [
            r"\b(perlu|harus|sebaiknya)\s+(belajar|perbaiki|tingkatkan|latihan)\w*\b",
            r"\b(lain kali|ke depan|next time)\b",
            r"\b(masih perlu|kurang|belum cukup)\b",
            r"\b(strategi|cara|metode)\s+(yang lebih|baru|berbeda)\b",
            r"\b(evaluasi|review|refleksi)\b",
            r"\b(perlu dipelajari lagi|lebih dalam lagi)",
            r"\b(learning point|takeaway)",
            r"\b(perlu (dilatih|dipraktikkan|diulang|dievaluasi|dipelajari)|harus (dilatih|diulang|diperbaiki|dipelajari lagi))\b",
            r"\b(mau belajar lagi|latih lagi|ulangi lagi|evaluasi diri|refleksi diri)\b",
        ],
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize with optional configuration for phase weights and sensitivity."""
        
        # Start with Zimmerman's standard defaults
        defaults = {
            "phase_weights": {
                SRLPhase.FORETHOUGHT: 1.2,
                SRLPhase.PERFORMANCE: 1.0,
                SRLPhase.REFLECTION: 1.3,
            },
            "scaffolding_levels": {
                SRLPhase.FORETHOUGHT: "high",
                SRLPhase.PERFORMANCE: "medium",
                SRLPhase.REFLECTION: "low",
            },
            "intervention_hints": {
                SRLPhase.FORETHOUGHT: "Goal clarification & planning support",
                SRLPhase.PERFORMANCE: "Strategy validation & monitoring check-in",
                SRLPhase.REFLECTION: "Metacognitive reflection prompt",
            },
            "confidence_min": 0.3,
            "confidence_max": 0.95,
            "enable_pattern_tracking": True,
            "max_matched_patterns": 10,
            "weight_multiplier": 1.5,
        }
        
        # Deep copy defaults into config
        self.config = {}
        for key, value in defaults.items():
            if isinstance(value, dict):
                self.config[key] = value.copy()
            else:
                self.config[key] = value
        
        # Apply custom config if provided
        if config:
            self._apply_config(config)

    def _apply_config(self, config: Dict[str, Any]):
        """Apply configuration updates dynamically."""
        
        if "phase_weights" in config:
            self.config["phase_weights"].update(config["phase_weights"])
        
        if "scaffolding_levels" in config:
            self.config["scaffolding_levels"].update(config["scaffolding_levels"])
        
        if "intervention_hints" in config:
            self.config["intervention_hints"].update(config["intervention_hints"])
        
        if "confidence_min" in config:
            self.config["confidence_min"] = config["confidence_min"]
        
        if "confidence_max" in config:
            self.config["confidence_max"] = config["confidence_max"]
        
        if "enable_pattern_tracking" in config:
            self.config["enable_pattern_tracking"] = config["enable_pattern_tracking"]
        
        if "max_matched_patterns" in config:
            self.config["max_matched_patterns"] = config["max_matched_patterns"]
        
        if "weight_multiplier" in config:
            self.config["weight_multiplier"] = config["weight_multiplier"]


    def classify(self, message: str) -> EnhancedSRLClassificationResult:
        """Classify message into Zimmerman phase with enhanced features."""

        if not message or not message.strip():
            return self._create_default_result()

        message_lower = message.lower()
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
            * self.config["phase_weights"][SRLPhase.FORETHOUGHT],
            SRLPhase.PERFORMANCE: performance_score
            * self.config["phase_weights"][SRLPhase.PERFORMANCE],
            SRLPhase.REFLECTION: reflection_score
            * self.config["phase_weights"][SRLPhase.REFLECTION],
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
        scaffolding_level = self.config["scaffolding_levels"][winning_phase]
        intervention_hint = self.config["intervention_hints"][winning_phase]

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
            matched_patterns=matched_patterns[:self.config["max_matched_patterns"]],  # Limit to top 10 matches
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
                        indicator = f"forethought:{sub_phase}" if "goal_setting" in sub_phase or "planning" in sub_phase else (f"performance:{sub_phase}" if "strategy_execution" in sub_phase or "monitoring_control" in sub_phase else f"reflection:{sub_phase}")
                        if indicator not in indicators:
                            indicators.append(indicator)

                        # Track matched patterns for debugging
                        matched_patterns.append(pattern)
                except re.error as e:
                    logger.warning(f"Invalid regex pattern: {pattern}, error: {e}")

            if count > 0:
                total_score += count * self.config["weight_multiplier"]  # Weight multiple matches

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
            "scaffolding_action": self._get_scaffolding_action(result.phase, result.confidence),
            "intervention_type": self._suggest_intervention(result.phase),
            "follow_up_needed": result.requires_attention,
            "priority_level": self._calculate_priority(result.confidence, result.phase),
        }

        return recommendations

    def _get_scaffolding_action(self, phase: SRLPhase, confidence: float = 0.5) -> str:
        """Get recommended scaffolding action per phase with dynamic adjustment."""
        
        base_actions = {
            SRLPhase.FORETHOUGHT: "Guide goal-setting, provide planning templates",
            SRLPhase.PERFORMANCE: "Monitor progress, validate strategies, offer examples",
            SRLPhase.REFLECTION: "Prompt metacognitive questions, encourage self-assessment",
        }
        
        base_action = base_actions.get(phase, "Provide standard support")
        
        # Dynamic adjustment based on confidence
        if confidence < 0.4:
            # Low confidence - increase scaffolding intensity
            intensified_actions = {
                SRLPhase.FORETHOUGHT: "INTENSIVE: Provide explicit goal-setting framework + visual planning aid",
                SRLPhase.PERFORMANCE: "INTENSIVE: Step-by-step strategy walkthrough + real-time monitoring",
                SRLPhase.REFLECTION: "INTENSIVE: Guided reflection template + structured self-assessment rubric",
            }
            return intensified_actions.get(phase, "Provide intensive support")
        if confidence > 0.8:
            # High confidence - reduce scaffolding
            reduced_actions = {
                SRLPhase.FORETHOUGHT: "Light guidance only - trust student goal clarity",
                SRLPhase.PERFORMANCE: "Minimal intervention - allow autonomous strategy execution",
                SRLPhase.REFLECTION: "Student-led reflection - facilitator just listens",
            }
            return reduced_actions.get(phase, "Offer minimal support")
        # Medium confidence - use default scaffolding
        return base_action

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
        if confidence > 0.7 and phase == SRLPhase.REFLECTION:
            return "HIGH"
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
