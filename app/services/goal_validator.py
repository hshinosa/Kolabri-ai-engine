"""
SMART Goal Validation Service
=============================
Validates learning goals against SMART criteria:
- S: Specific (operational verbs from Bloom's Taxonomy)
- M: Measurable (numeric metrics)
- A: Achievable
- R: Relevant
- T: Time-bound (deadline indicators)
"""

import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from app.core.logging import get_logger

logger = get_logger(__name__)


class SMARTCriterion(str, Enum):
    """SMART criteria enum"""

    SPECIFIC = "specific"
    MEASURABLE = "measurable"
    ACHIEVABLE = "achievable"
    RELEVANT = "relevant"
    TIME_BOUND = "time_bound"


@dataclass
class SMARTValidationResult:
    """Result of SMART goal validation"""

    is_valid: bool
    score: float  # 0.0 - 1.0 (percentage of met criteria)
    feedback: str
    missing_criteria: List[str]
    details: Dict[str, bool]
    suggestions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)


def strip_markdown_json_fence(content: str) -> str:
    """Remove optional ``` / ```json fences from an LLM JSON payload."""
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.split("\n")
    start = 1 if lines[0].startswith("```") else 0
    end = len(lines) - 1 if lines and lines[-1].strip() == "```" else len(lines)
    return "\n".join(lines[start:end]).strip()


class GoalValidator:
    """
    Service to validate learning goals against SMART criteria.

    Uses a combination of:
    - Regex patterns for keyword detection
    - Bloom's Taxonomy operational verbs
    - NLP heuristics for context understanding
    """

    # Operational verbs for 'Specific' criteria (Bloom's Taxonomy)
    # Covers all levels: Remember, Understand, Apply, Analyze, Evaluate, Create
    OPERATIONAL_VERBS = [
        # Remember
        "mengingat",
        "menyebutkan",
        "mengidentifikasi",
        "mendefinisikan",
        "menghafal",
        "mencatat",
        "menemukan",
        # Understand
        "menjelaskan",
        "menggambarkan",
        "meringkas",
        "menginterpretasikan",
        "membedakan",
        "mencontohkan",
        "mengklasifikasikan",
        # Apply
        "menerapkan",
        "menggunakan",
        "melaksanakan",
        "mengimplementasikan",
        "mendemonstrasikan",
        "mengoperasikan",
        # Analyze
        "menganalisis",
        "membandingkan",
        "membedakan",
        "mengorganisir",
        "menemukan",
        "menguji",
        "memeriksa",
        # Evaluate
        "mengevaluasi",
        "menilai",
        "mengkritik",
        "menimbang",
        "memutuskan",
        "memilih",
        "mendukung",
        # Create
        "membuat",
        "merancang",
        "menyusun",
        "mengembangkan",
        "merumuskan",
        "membangun",
        "menciptakan",
        "mendesain",
        # Additional specific verbs
        "menulis",
        "menghitung",
        "menggambar",
        "memetakan",
    ]

    # Measurable indicators (numbers, units, percentages)
    MEASURABLE_PATTERNS = [
        r"\d+",  # Any number (e.g., "10 halaman")
        r"persen|%",  # Percentage
        r"halaman|lembar|buah|unit",  # Count units
        r"jam|menit|detik",  # Time units
        r"point|poin|nilai|skor",  # Score units
        r"minimal|maksimal|target",  # Quantity qualifiers
    ]

    # Time-bound indicators
    TIME_BOUND_PATTERNS = [
        r"minggu|bulan|tahun",  # Relative time periods
        r"hari|senin|selasa|rabu|kamis|jumat|sabtu|minggu",  # Days
        r"besok|lusa",  # Near future (removed 'nanti' as it's too vague)
        r"deadline|batas waktu",  # Explicit deadlines
        r"tanggal \d+",  # Specific dates
        r"\d{1,2}/\d{1,2}(/\d{2,4})?",  # Date format (DD/MM/YYYY)
        r"sampai|hingga|sebelum",  # Time boundaries
    ]

    # Context keywords that indicate goal-setting intent
    GOAL_KEYWORDS = [
        "ingin",
        "target",
        "tujuan",
        "akan",
        "hendak",
        "rencana",
        "berencana",
        "bermaksud",
        "goal",
    ]

    def __init__(self):
        """Initialize GoalValidator"""
        logger.info("GoalValidator initialized")

    def is_goal_statement(self, text: str) -> bool:
        """
        Detect if the text is a goal-setting statement.

        Args:
            text: Input text to check

        Returns:
            True if text contains goal-setting keywords
        """
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.GOAL_KEYWORDS)

    def check_specific(self, text: str) -> bool:
        """
        Check if goal contains specific operational verbs.

        Args:
            text: Goal text

        Returns:
            True if contains operational verb from Bloom's Taxonomy
        """
        text_lower = text.lower()
        has_verb = any(verb in text_lower for verb in self.OPERATIONAL_VERBS)

        if has_verb:
            logger.debug("smart_check_specific", result=True, text=text[:50])

        return has_verb

    def check_measurable(self, text: str) -> bool:
        """
        Check if goal contains measurable metrics.

        Args:
            text: Goal text

        Returns:
            True if contains numbers or quantifiable units
        """
        text_lower = text.lower()

        for pattern in self.MEASURABLE_PATTERNS:
            if re.search(pattern, text_lower):
                logger.debug(
                    "smart_check_measurable",
                    result=True,
                    pattern=pattern,
                    text=text[:50],
                )
                return True

        return False

    def check_time_bound(self, text: str) -> bool:
        """
        Check if goal contains time constraints.

        Args:
            text: Goal text

        Returns:
            True if contains deadline or time period
        """
        text_lower = text.lower()

        for pattern in self.TIME_BOUND_PATTERNS:
            if re.search(pattern, text_lower):
                logger.debug(
                    "smart_check_time_bound",
                    result=True,
                    pattern=pattern,
                    text=text[:50],
                )
                return True

        return False

    def validate_goal(self, text: str) -> SMARTValidationResult:
        """
        Validate a learning goal against SMART criteria.

        Args:
            text: The goal text to validate

        Returns:
            SMARTValidationResult with validation details and feedback
        """
        logger.info("validating_goal", text=text[:100])

        # Check each criterion
        details = {
            SMARTCriterion.SPECIFIC.value: self.check_specific(text),
            SMARTCriterion.MEASURABLE.value: self.check_measurable(text),
            SMARTCriterion.TIME_BOUND.value: self.check_time_bound(text),
            # Achievable and Relevant are implicit (require LLM judgment)
            # We assume True for now unless obviously unrealistic
            SMARTCriterion.ACHIEVABLE.value: True,
            SMARTCriterion.RELEVANT.value: True,
        }

        # Identify missing criteria (only check S, M, T programmatically)
        checked_criteria = [
            SMARTCriterion.SPECIFIC,
            SMARTCriterion.MEASURABLE,
            SMARTCriterion.TIME_BOUND,
        ]
        missing = [
            criterion.value
            for criterion in checked_criteria
            if not details[criterion.value]
        ]

        # Calculate score based on met criteria out of total checked
        score = sum(details[c.value] for c in checked_criteria) / len(checked_criteria)

        # All checked criteria must be met for validity
        is_valid = len(missing) == 0

        # Generate feedback and suggestions
        feedback, suggestions = self._generate_feedback(details, missing, text)

        result = SMARTValidationResult(
            is_valid=is_valid,
            score=score,
            feedback=feedback,
            missing_criteria=missing,
            details=details,
            suggestions=suggestions,
        )

        logger.info(
            "goal_validation_complete", is_valid=is_valid, score=score, missing=missing
        )

        return result

    def _generate_feedback(
        self, details: Dict[str, bool], missing: List[str], text: str
    ) -> tuple[str, List[str]]:
        """
        Generate human-readable feedback and improvement suggestions.

        Args:
            details: Validation details for each criterion
            missing: List of missing criteria
            text: Original goal text

        Returns:
            Tuple of (feedback message, list of suggestions)
        """
        suggestions = []

        if not missing:
            feedback = "✅ Tujuan Anda sudah memenuhi kriteria SMART! Silakan lanjutkan dengan diskusi kelompok."
        else:
            feedback = f"⚠️ Tujuan Anda masih kurang: {', '.join(missing).upper()}."

            # Generate specific suggestions for each missing criterion
            if SMARTCriterion.SPECIFIC.value in missing:
                suggestions.append(
                    "SPECIFIC: Gunakan kata kerja operasional yang jelas. "
                    "Contoh: 'membuat', 'menganalisis', 'merancang', 'menulis'."
                )

            if SMARTCriterion.MEASURABLE.value in missing:
                suggestions.append(
                    "MEASURABLE: Tambahkan target yang dapat diukur. "
                    "Contoh: '10 halaman', '5 prototype', 'minimal 80%'."
                )

            if SMARTCriterion.TIME_BOUND.value in missing:
                suggestions.append(
                    "TIME-BOUND: Tentukan batas waktu yang jelas. "
                    "Contoh: 'minggu depan', 'dalam 3 hari', 'sebelum tanggal 15'."
                )

        return feedback, suggestions

    def get_improvement_hints(self, validation_result: SMARTValidationResult) -> str:
        """
        Get Socratic questioning hints to guide student improvement.

        Args:
            validation_result: Validation result with missing criteria

        Returns:
            Scaffolding question to prompt student thinking
        """
        missing = validation_result.missing_criteria

        if not missing:
            return (
                "Tujuan Anda sudah SMART. Apa langkah pertama yang akan Anda lakukan?"
            )

        # Prioritize the first missing criterion
        first_missing = missing[0]

        hints = {
            SMARTCriterion.SPECIFIC.value: (
                "Apa yang *secara spesifik* ingin Anda hasilkan atau capai? "
                "Coba gunakan kata kerja yang lebih konkret."
            ),
            SMARTCriterion.MEASURABLE.value: (
                "Bagaimana Anda tahu sudah berhasil? "
                "Berapa *jumlah* atau *target* yang ingin dicapai?"
            ),
            SMARTCriterion.TIME_BOUND.value: (
                "*Kapan* Anda ingin mencapai tujuan ini? "
                "Tentukan batas waktu yang realistis."
            ),
        }

        return hints.get(first_missing, "Coba perjelas tujuan Anda agar lebih terukur.")

    async def generate_llm_hint(
        self,
        goal_text: str,
        missing_criteria: List[str],
        week_context: Optional[Dict[str, Any]] = None,
        week_off_topic: bool = False,
    ) -> Optional[str]:
        try:
            logger.info(
                "generating_llm_hint",
                goal_text=goal_text[:80],
                missing_criteria=missing_criteria,
                has_week_context=week_context is not None,
            )

            from app.services.llm import get_llm_service
            from app.core.prompt_templates import SYSTEM_GOAL_HINT

            llm = get_llm_service()
            week_title = (week_context or {}).get("week_title", "topik minggu ini")
            material_titles = (week_context or {}).get("material_titles") or []
            mats_str = (
                ", ".join(material_titles[:5]) if material_titles else "belum ada"
            )

            system_prompt = SYSTEM_GOAL_HINT.format(
                missing_criteria=", ".join(missing_criteria),
                week_title=week_title,
                material_titles=mats_str,
                goal_text=goal_text,
            )

            off_topic_note = ""
            if week_off_topic:
                off_topic_note = (
                    f"\n\nPENTING: Goal mahasiswa TIDAK SELARAS dengan materi minggu ini "
                    f"({week_title}: {mats_str}). "
                    f"Bimbing mahasiswa untuk menghubungkan goal dengan topik minggu ini."
                )

            prompt = (
                f'Goal mahasiswa: "{goal_text}"\n'
                f"Kriteria yang kurang: {', '.join(missing_criteria)}"
                f"{off_topic_note}\n"
                f"Berikan satu pertanyaan Socratic singkat untuk membimbingnya."
            )

            response = await llm.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=250,
            )

            logger.info(
                "llm_hint_response",
                success=response.success,
                content_length=len(response.content) if response.content else 0,
                content_preview=response.content[:100] if response.content else None,
                error=response.error if hasattr(response, "error") else None,
            )

            if response.success and response.content.strip():
                hint = response.content.strip().strip('"').strip("'")
                if len(hint) > 200:
                    hint = hint[:197] + "..."
                logger.info("llm_hint_generated", hint=hint)
                return hint

            logger.warning("llm_hint_empty_response", success=response.success)
            return None
        except Exception as e:
            logger.exception(
                "llm_goal_hint_failed", goal_text=goal_text[:80], error=str(e)
            )
            return None

    async def refine_goal(
        self, current_goal: str, missing_criteria: List[str]
    ) -> Dict[str, Any]:
        """
        Refine a learning goal using LLM to address missing SMART criteria.

        Args:
            current_goal: The current goal text that needs refinement
            missing_criteria: List of missing SMART criteria

        Returns:
            Dictionary with refined goal and metadata
        """
        logger.info(
            "refining_goal",
            current_goal=current_goal[:100],
            missing_criteria=missing_criteria,
        )

        try:
            from app.services.llm import get_llm_service
            from app.core.prompt_templates import (
                COT_GOAL_REFINEMENT,
                SYSTEM_GOAL_REFINEMENT,
                TEMPERATURE,
            )

            llm = get_llm_service()

            prompt = COT_GOAL_REFINEMENT.format(
                current_goal=current_goal, missing_criteria=", ".join(missing_criteria)
            )

            response = await llm.generate(
                prompt=prompt,
                system_prompt=SYSTEM_GOAL_REFINEMENT,
                temperature=TEMPERATURE["goal_refinement"],
            )

            # Parse JSON response
            import json
            import sys

            try:
                # Ensure response content is properly encoded
                # Fix Windows encoding issue by using UTF-8 explicitly
                content = response.content
                if isinstance(content, str):
                    # Try to encode as UTF-8, replace any problematic characters
                    try:
                        content = content.encode("utf-8", errors="replace").decode(
                            "utf-8"
                        )
                    except Exception:
                        # If that fails, use ASCII with replacement
                        content = content.encode("ascii", errors="replace").decode(
                            "ascii"
                        )
                content = strip_markdown_json_fence(content)

                result = json.loads(content)

                # Log the parsed result for debugging
                logger.info("json_parsed_successfully", keys=list(result.keys()))

                # Check if the expected key exists, if not try to find alternative keys
                if "refined_goal" not in result:
                    # Try to find alternative key names
                    possible_keys = [
                        "goal",
                        "refined",
                        "suggested_goal",
                        "improved_goal",
                        "new_goal",
                    ]
                    found_key = None
                    for key in possible_keys:
                        if key in result:
                            found_key = key
                            break

                    if found_key:
                        logger.warning(
                            "json_key_not_found",
                            expected="refined_goal",
                            found=found_key,
                        )
                        # Rename the key to match expected format
                        result["refined_goal"] = result[found_key]
                    else:
                        logger.error(
                            "json_missing_required_key",
                            available_keys=list(result.keys()),
                        )
                        raise KeyError(
                            f"Missing 'refined_goal' key in JSON response. Available keys: {list(result.keys())}"
                        )

                refined_goal_text = result["refined_goal"]

                if not isinstance(refined_goal_text, str):
                    logger.error(
                        "refined_goal_not_string", type=type(refined_goal_text).__name__
                    )
                    raise TypeError(
                        f"refined_goal must be a string, got {type(refined_goal_text).__name__}"
                    )

                logger.info(
                    "validating_refined_goal", refined_goal=refined_goal_text[:100]
                )

                validation = self.validate_goal(refined_goal_text)

                logger.info(
                    "goal_refined",
                    original=current_goal[:50],
                    refined=result["refined_goal"][:50],
                    is_valid=validation.is_valid,
                )

                return {
                    "success": True,
                    "refined_goal": result["refined_goal"],
                    "explanation": result.get("explanation", ""),
                    "suggestions": result.get("suggestions", []),
                    "validation": validation.to_dict(),
                    "tokens_used": response.tokens_used,
                }

            except json.JSONDecodeError:
                # If JSON parsing fails, return the raw response
                logger.warning("json_parse_failed", response=response.content[:100])

                return {
                    "success": False,
                    "error": "Failed to parse LLM response",
                    "raw_response": response.content,
                }

        except Exception:
            logger.exception("goal_refinement_failed")

            return {"success": False, "error": "Internal error"}

    def generate_socratic_hint(
        self,
        missing_criteria: List[str],
        goal_text: str = "",
        week_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate a contextual Socratic question to guide student to improve their goal."""
        if not missing_criteria:
            return "Tujuanmu sudah sangat bagus dan SMART! Kamu siap mulai belajar."

        import random

        week_title = (week_context or {}).get("week_title", "")
        material_titles = (week_context or {}).get("material_titles") or []

        goal_snippet = goal_text.strip()
        if len(goal_snippet) > 60:
            goal_snippet = goal_snippet[:57] + "..."

        hints: Dict[str, List[str]] = {}

        specific_hints: List[str] = []
        if week_title:
            specific_hints.append(
                f'Bagian mana dari "{week_title}" yang paling ingin kamu kuasai secara mendalam?'
            )
        if material_titles:
            mat_sample = random.choice(material_titles[:5]) if material_titles else ""
            if mat_sample:
                specific_hints.append(
                    f'Coba hubungkan tujuanmu dengan materi "{mat_sample}" — aspek apa yang ingin kamu dalami?'
                )
        specific_hints.extend(
            [
                "Bisa lebih spesifik tentang bagian mana dari topik ini yang ingin kamu kuasai?",
                "Apa satu konsep atau teknik dari topik ini yang paling menantang bagimu?",
            ]
        )
        hints["specific"] = specific_hints

        measurable_hints: List[str] = []
        if goal_snippet:
            measurable_hints.append(
                f'Untuk "{goal_snippet}", bagaimana cara kamu mengukur bahwa tujuan ini sudah tercapai?'
            )
        if week_title:
            measurable_hints.append(
                f'Berapa banyak konsep dari "{week_title}" yang ingin kamu kuasai di akhir sesi diskusi?'
            )
        measurable_hints.extend(
            [
                "Indikator apa yang bisa kamu pakai untuk menilai pemahamanmu — misalnya bisa menjelaskan ke teman, atau mengerjakan soal latihan?",
                "Jika temanmu bertanya, bukti konkret apa yang bisa kamu tunjukkan bahwa tujuan ini tercapai?",
            ]
        )
        hints["measurable"] = measurable_hints

        time_hints: List[str] = []
        if week_title:
            time_hints.append(
                f'Kapan kamu ingin selesai membahas "{week_title}" — sebelum diskusi berikutnya atau dalam sesi ini saja?'
            )
        time_hints.extend(
            [
                "Berapa lama waktu yang akan kamu alokasikan untuk mencapai target ini?",
                "Apakah target ini ingin kamu capai dalam satu sesi diskusi atau bertahap?",
            ]
        )
        hints["time_bound"] = time_hints

        achievable_hints: List[str] = []
        if goal_snippet:
            achievable_hints.append(
                f'"{goal_snippet}" terlihat cukup luas — bisa dipersempit jadi satu aspek yang paling prioritas?'
            )
        if material_titles:
            achievable_hints.append(
                f"Dengan {len(material_titles)} materi yang tersedia, mana yang paling realistis untuk dikuasai dalam satu sesi?"
            )
        achievable_hints.extend(
            [
                "Apakah target ini sudah pas untuk satu sesi diskusi, atau perlu dipecah jadi beberapa langkah?",
            ]
        )
        hints["achievable"] = achievable_hints

        relevant_hints: List[str] = []
        if week_title:
            relevant_hints.append(
                f'Mengapa topik "{week_title}" penting untuk dipahami dalam konteks matakuliah ini?'
            )
        relevant_hints.append(
            "Bagaimana tujuan ini mendukung pemahamanmu di topik berikutnya?"
        )
        hints["relevant"] = relevant_hints

        # Pick one missing criterion to focus on (scaffolding approach)
        primary_missing = missing_criteria[0]
        hint_list = hints.get(
            primary_missing, ["Coba kembangkan lagi tujuanmu agar lebih mendetail."]
        )

        return random.choice(hint_list)


# Singleton instance
_goal_validator: Optional[GoalValidator] = None


def get_goal_validator() -> GoalValidator:
    """
    Get singleton instance of GoalValidator.

    Returns:
        GoalValidator instance
    """
    global _goal_validator
    if _goal_validator is None:
        _goal_validator = GoalValidator()
    return _goal_validator
