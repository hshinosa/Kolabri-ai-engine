"""
Guardrails Service - AI Safety & Content Moderation
Kolabri AI Engine

Implements safety guardrails for AI responses:
- Academic dishonesty detection (prevent homework completion)
- Off-topic query detection
- Toxicity and PII filtering
- Input validation and sanitization
"""

import re
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from app.core.logging import get_logger
from app.services.injection_detector import InjectionDetector
from app.services.toxicity_scorer import ToxicityScorer
from app.services.pii_detector import PIIDetector

logger = get_logger(__name__)


class GuardrailAction(Enum):
    """Actions that guardrails can take."""

    ALLOW = "allow"  # Allow the query to proceed
    BLOCK = "block"  # Block completely with rejection message
    WARN = "warn"  # Allow but with warning
    REDIRECT = "redirect"  # Redirect to appropriate response
    SANITIZE = "sanitize"  # Clean the input and proceed


@dataclass
class GuardrailResult:
    """Result from guardrail check."""

    action: GuardrailAction
    reason: str
    message: Optional[str] = None  # Message to show user if blocked
    sanitized_input: Optional[str] = None  # Cleaned input if sanitized
    confidence: float = 1.0  # Confidence in the decision
    triggered_rules: List[str] = field(
        default_factory=list
    )  # List of rules that were triggered


class Guardrails:
    """
    Guardrails for AI safety and content moderation.

    Implements Teacher-AI Complementarity principle:
    - AI assists learning, doesn't replace student effort
    - Prevents academic dishonesty
    - Maintains educational context
    """

    NON_CRITICAL_REASONS = {
        "academic_dishonesty_detected",
        "off_topic_detected",
        "direct_answer_detected",
        "complete_solution_detected",
        "pii_in_response",
    }

    @staticmethod
    def _policy_value(policy: Optional[dict[str, Any]], key: str, default: Any) -> Any:
        if not policy:
            return default
        return policy[key] if key in policy else default

    def _apply_policy(
        self,
        result: GuardrailResult,
        *,
        context: Optional[dict[str, Any]] = None,
        surface: str = "input",
    ) -> GuardrailResult:
        policy = (context or {}).get("guardrail_policy") or {}

        if (
            result.reason not in self.NON_CRITICAL_REASONS
            and result.action == GuardrailAction.BLOCK
        ):
            return result

        if self._policy_value(policy, "allow_flag_only", False) and result.action in [
            GuardrailAction.BLOCK,
            GuardrailAction.REDIRECT,
            GuardrailAction.SANITIZE,
        ]:
            return GuardrailResult(
                action=GuardrailAction.WARN,
                reason=result.reason,
                message="Interaksi ini ditandai oleh kebijakan AI course ini. Tinjau hasilnya dengan hati-hati.",
                confidence=result.confidence,
                triggered_rules=result.triggered_rules,
            )

        if (
            surface == "output"
            and self._policy_value(policy, "allow_rewrite", False)
            and result.action in [GuardrailAction.BLOCK, GuardrailAction.REDIRECT]
        ):
            return GuardrailResult(
                action=GuardrailAction.SANITIZE,
                reason=result.reason,
                sanitized_input="Saya tidak bisa memberi jawaban langsung untuk permintaan itu. Saya bisa bantu dengan petunjuk, langkah belajar, atau ringkasan konsepnya.",
                message="Jawaban disesuaikan oleh kebijakan AI course ini.",
                confidence=result.confidence,
                triggered_rules=result.triggered_rules,
            )

        return result

    # ==================== Academic Dishonesty Detection ====================

    # Patterns that indicate request for homework completion
    HOMEWORK_PATTERNS = [
        # Indonesian patterns
        r"\b(buatkan|kerjakan|selesaikan)\s+(saya\s+)?(esai|tugas|makalah|laporan|pr|pekerjaan rumah)\b",
        r"\b(tolong\s+)?kerjakan\s+untuk\s+(saya|aku)\b",
        r"\bjawab(kan)?\s+(semua\s+)?soal\b",
        r"\bbuatkan\s+(saya\s+)?(kode|code|program|script)\s+lengkap\b",
        r"\bselesaikan\s+assignment\b",
        r"\bbuatkan\s+presentasi\b",
        r"\btulis(kan)?\s+(saya\s+)?(esai|makalah|paper)\b",
        r"\bcarikan\s+jawaban\s+(ujian|quiz|kuis)\b",
        r"\bberikan\s+contoh\s+jawaban\s+lengkap\b",
        # English patterns
        r"\b(write|do|complete)\s+(my|the)\s+(essay|assignment|homework|paper|report)\b",
        r"\bsolve\s+(this|my)\s+(problem|assignment|homework)\s+for\s+me\b",
        r"\bdo\s+my\s+homework\b",
        r"\bwrite\s+my\s+code\b",
        r"\bcomplete\s+this\s+assignment\b",
        r"\bgive\s+me\s+the\s+answers?\b",
        r"\banswer\s+(all\s+)?these?\s+questions?\s+for\s+me\b",
    ]

    # Keywords that indicate potential cheating intent
    CHEATING_KEYWORDS = [
        "jawaban ujian",
        "kunci jawaban",
        "bocoran soal",
        "contek",
        "nyontek",
        "exam answers",
        "test answers",
        "cheat",
        "plagiarize",
        "copy paste",
        "tulis ulang persis",
        "salin",
        "copy langsung",
    ]

    # ==================== Acceptable Educational Requests ====================

    # Patterns for legitimate learning requests (should NOT be blocked)
    LEARNING_PATTERNS = [
        r"\bjelaskan\s+(konsep|materi|cara)\b",
        r"\bapa\s+(itu|yang dimaksud)\b",
        r"\bbagaimana\s+(cara|langkah)\b",
        r"\bmengapa\b",
        r"\bcontoh\s+(dari|untuk)\b",
        r"\bbantu\s+(saya\s+)?memahami\b",
        r"\btolong\s+jelaskan\b",
        r"\bexplain\b",
        r"\bwhat\s+is\b",
        r"\bhow\s+(do|does|to)\b",
        r"\bwhy\b",
        r"\bhelp\s+me\s+understand\b",
    ]

    # ==================== Off-Topic Detection ====================

    # Topics that are clearly off-topic for educational context
    OFF_TOPIC_PATTERNS = [
        # Personal/social
        r"\b(pacar|gebetan|pdkt|jodoh|cinta|relationship)\b",
        r"\b(gossip|gosip|drama|artis|selebritis)\b",
        # Harmful content
        r"\b(bunuh|suicide|self-harm|melukai diri)\b",
        r"\b(narkoba|drugs|obat terlarang)\b",
        r"\b(senjata|weapon|bom|explosive)\b",
        r"\b(hack|hacking|crack|illegal)\b",
        # Adult content
        r"\b(porn|xxx|adult content|konten dewasa)\b",
        r"\b(gambling|judi|taruhan)\b",
        # Political/religious extremism
        r"\b(teror|terrorism|radikal|extremist)\b",
    ]

    # ==================== PII Detection ====================

    # Patterns for Personally Identifiable Information
    PII_PATTERNS = [
        # Indonesian ID numbers
        (r"\b\d{16}\b", "NIK/KTP"),  # NIK
        (r"\b\d{2}\.\d{3}\.\d{3}\.\d{1}-\d{3}\.\d{3}\b", "NPWP"),  # NPWP
        # Phone numbers
        (r"\b(\+62|62|0)8[1-9][0-9]{7,10}\b", "Phone"),
        # Email (for warning, not blocking)
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "Email"),
        # Credit card (basic pattern)
        (r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", "Credit Card"),
        # Passwords in text
        (r"\b(password|kata sandi|pw|pass)[\s:]+\S+\b", "Password"),
    ]

    # ==================== Toxicity Keywords ====================

    TOXICITY_KEYWORDS = [
        # Indonesian profanity (mild list)
        "bodoh",
        "goblok",
        "tolol",
        "idiot",
        "bego",
        "anjing",
        "bangsat",
        "kampret",
        "bajingan",
        "brengsek",
        "sialan",
        # English profanity (common)
        "stupid",
        "idiot",
        "dumb",
        "moron",
        "fuck",
        "shit",
        "damn",
        "bastard",
        "asshole",
        "bitch",
    ]

    # ==================== Response Messages ====================

    REJECTION_MESSAGES = {
        "homework": """Maaf, saya tidak bisa mengerjakan tugas untuk Anda secara langsung. 🎓

Namun, saya bisa membantu Anda dengan cara:
• Menjelaskan konsep yang belum dipahami
• Memberikan contoh serupa untuk dipelajari
• Membantu memahami langkah-langkah penyelesaian
• Menjawab pertanyaan spesifik tentang materi

Apa yang ingin Anda pahami lebih dalam?""",
        "cheating": """Maaf, saya tidak bisa membantu dengan hal tersebut karena melanggar integritas akademik. 📚

Saya di sini untuk mendukung pembelajaran Anda, bukan menggantikan usaha belajar Anda sendiri.

Silakan ajukan pertanyaan tentang konsep atau materi yang ingin Anda pahami!""",
        "off_topic": """Pertanyaan Anda tampaknya di luar konteks pembelajaran di kelas ini. 📖

Saya adalah asisten pembelajaran yang fokus membantu Anda memahami materi perkuliahan.

Ada pertanyaan tentang materi kuliah yang bisa saya bantu?""",
        "harmful": """Maaf, saya tidak bisa membantu dengan pertanyaan tersebut. ⚠️

Jika Anda membutuhkan bantuan terkait kesehatan mental atau situasi darurat, 
silakan hubungi layanan profesional yang sesuai.

Hotline Kesehatan Jiwa: 119 ext. 8""",
        "pii_warning": """⚠️ Perhatian: Pesan Anda mungkin mengandung informasi pribadi ({pii_type}).

Untuk keamanan Anda, hindari membagikan:
• Nomor identitas (KTP, SIM, Paspor)
• Nomor telepon atau alamat
• Informasi keuangan
• Password atau kredensial

Pertanyaan Anda akan tetap diproses, tetapi harap berhati-hati.""",
        "toxicity": """Mohon gunakan bahasa yang sopan dan konstruktif dalam diskusi. 🤝

Diskusi yang baik membutuhkan komunikasi yang saling menghargai.
Mari fokus pada pembelajaran bersama!""",
    }

    def __init__(self):
        """Initialize guardrails with compiled patterns."""
        # Compile regex patterns for efficiency
        self._homework_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.HOMEWORK_PATTERNS
        ]
        self._learning_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.LEARNING_PATTERNS
        ]
        self._off_topic_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.OFF_TOPIC_PATTERNS
        ]
        self._pii_patterns = [
            (re.compile(p, re.IGNORECASE), label) for p, label in self.PII_PATTERNS
        ]
        self._injection_detector = InjectionDetector()
        self._toxicity_scorer = ToxicityScorer()
        self._pii_detector = PIIDetector()

        logger.info("guardrails_initialized")

    def check_input(
        self, text: str, context: Optional[dict[str, Any]] = None
    ) -> GuardrailResult:
        """
        Run all guardrail checks on input text.

        Args:
            text: Input text to check
            context: Optional context (course_id, user_role, etc.)

        Returns:
            GuardrailResult with action and details
        """
        context = context or {}
        text_lower = text.lower().strip()
        triggered_rules = []

        # 0. Check for prompt injection first
        injection_result = self._check_prompt_injection(text)
        if injection_result.action == GuardrailAction.BLOCK:
            logger.warning(
                "guardrail_blocked", reason="prompt_injection", text_preview=text[:50]
            )
            return injection_result
        if injection_result.triggered_rules:
            triggered_rules.extend(injection_result.triggered_rules)

        # 1. Check for harmful content first (highest priority)
        harmful_result = self._check_harmful_content(text_lower)
        if harmful_result.action == GuardrailAction.BLOCK:
            logger.warning(
                "guardrail_blocked", reason="harmful_content", text_preview=text[:50]
            )
            return harmful_result

        # 2. Check for academic dishonesty
        homework_result = self._check_academic_dishonesty(text, text_lower)
        if homework_result.action == GuardrailAction.BLOCK:
            logger.warning(
                "guardrail_blocked",
                reason="academic_dishonesty",
                text_preview=text[:50],
            )
            return self._apply_policy(homework_result, context=context)
        if homework_result.triggered_rules:
            triggered_rules.extend(homework_result.triggered_rules)

        # 3. Check for off-topic content
        offtopic_result = self._check_off_topic(text_lower)
        if offtopic_result.action == GuardrailAction.BLOCK:
            logger.warning(
                "guardrail_blocked", reason="off_topic", text_preview=text[:50]
            )
            return self._apply_policy(offtopic_result, context=context)
        if offtopic_result.triggered_rules:
            triggered_rules.extend(offtopic_result.triggered_rules)

        # 4. Check for PII (warning, not blocking)
        pii_result = self._check_pii(text)
        if pii_result.action == GuardrailAction.WARN:
            logger.info(
                "guardrail_pii_warning",
                pii_types=pii_result.triggered_rules,
                text_preview=text[:50],
            )
            # Continue but with warning
            triggered_rules.extend(pii_result.triggered_rules)

        # 5. Check for toxicity (warning or sanitize)
        toxicity_result = self._check_toxicity(text_lower)
        if toxicity_result.action in [GuardrailAction.WARN, GuardrailAction.SANITIZE]:
            logger.info(
                "guardrail_toxicity_detected",
                action=toxicity_result.action.value,
                text_preview=text[:50],
            )
            if toxicity_result.triggered_rules:
                triggered_rules.extend(toxicity_result.triggered_rules)

        # All checks passed
        logger.debug("guardrail_passed", text_preview=text[:50])

        if pii_result.action == GuardrailAction.WARN and self._policy_value(
            context.get("guardrail_policy"), "allow_flag_only", False
        ):
            return GuardrailResult(
                action=GuardrailAction.WARN,
                reason="pii_warning",
                message="Interaksi ini ditandai oleh kebijakan AI course ini karena mengandung data sensitif.",
                triggered_rules=triggered_rules if triggered_rules else [],
            )

        return GuardrailResult(
            action=GuardrailAction.ALLOW,
            reason="all_checks_passed",
            triggered_rules=triggered_rules if triggered_rules else [],
            sanitized_input=toxicity_result.sanitized_input
            if toxicity_result.sanitized_input
            else text,
        )

    def _check_prompt_injection(self, text: str) -> GuardrailResult:
        """Detect prompt injection patterns using the injection detector."""
        result = self._injection_detector.score(text)
        if result.is_injection:
            return GuardrailResult(
                action=GuardrailAction.BLOCK,
                reason="prompt_injection_detected",
                message=self.REJECTION_MESSAGES["cheating"],
                triggered_rules=[f"prompt_injection:{r}" for r in result.reasons],
                confidence=result.score,
            )

        return GuardrailResult(
            action=GuardrailAction.ALLOW,
            reason="no_prompt_injection",
            confidence=max(0.0, 1.0 - result.score),
            triggered_rules=[f"prompt_injection:{r}" for r in result.reasons]
            if result.reasons
            else [],
        )

    def _check_academic_dishonesty(self, text: str, text_lower: str) -> GuardrailResult:
        """Check for homework completion or cheating requests."""
        triggered = []

        # First, check if it's a legitimate learning request
        for pattern in self._learning_patterns:
            if pattern.search(text_lower):
                # Likely a legitimate question, allow it
                return GuardrailResult(
                    action=GuardrailAction.ALLOW, reason="legitimate_learning_request"
                )

        # Check for homework completion patterns
        for pattern in self._homework_patterns:
            match = pattern.search(text_lower)
            if match:
                triggered.append(f"homework_pattern:{match.group()}")

        # Check for cheating keywords
        for keyword in self.CHEATING_KEYWORDS:
            if keyword in text_lower:
                triggered.append(f"cheating_keyword:{keyword}")

        if triggered:
            return GuardrailResult(
                action=GuardrailAction.BLOCK,
                reason="academic_dishonesty_detected",
                message=self.REJECTION_MESSAGES["homework"],
                triggered_rules=triggered,
                confidence=0.9 if len(triggered) > 1 else 0.75,
            )

        return GuardrailResult(
            action=GuardrailAction.ALLOW, reason="no_dishonesty_detected"
        )

    def _check_off_topic(self, text_lower: str) -> GuardrailResult:
        """Check for off-topic content."""
        triggered = []

        for pattern in self._off_topic_patterns:
            match = pattern.search(text_lower)
            if match:
                triggered.append(f"off_topic:{match.group()}")

        if triggered:
            return GuardrailResult(
                action=GuardrailAction.BLOCK,
                reason="off_topic_content",
                message=self.REJECTION_MESSAGES["off_topic"],
                triggered_rules=triggered,
                confidence=0.85,
            )

        return GuardrailResult(action=GuardrailAction.ALLOW, reason="on_topic")

    def _check_harmful_content(self, text_lower: str) -> GuardrailResult:
        """Check for harmful or dangerous content."""
        # Check for self-harm or violence indicators
        harmful_patterns = [
            r"\b(bunuh diri|suicide|self.?harm|melukai diri)\b",
            r"\b(cara membuat bom|how to make.*(bomb|weapon))\b",
            r"\b(cara membunuh|how to kill)\b",
        ]

        for pattern in harmful_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return GuardrailResult(
                    action=GuardrailAction.BLOCK,
                    reason="harmful_content",
                    message=self.REJECTION_MESSAGES["harmful"],
                    triggered_rules=[f"harmful:{pattern}"],
                    confidence=0.95,
                )

        return GuardrailResult(
            action=GuardrailAction.ALLOW, reason="no_harmful_content"
        )

    def _check_pii(self, text: str) -> GuardrailResult:
        """Check for Personally Identifiable Information."""
        result = self._pii_detector.detect(text)

        if result.has_pii:
            pii_list = ", ".join(result.labels)
            return GuardrailResult(
                action=GuardrailAction.WARN,
                reason="pii_detected",
                message=self.REJECTION_MESSAGES["pii_warning"].format(
                    pii_type=pii_list
                ),
                triggered_rules=result.labels,
                sanitized_input=result.masked_text,
                confidence=0.9,
            )

        return GuardrailResult(action=GuardrailAction.ALLOW, reason="no_pii_detected")

    def _check_toxicity(self, text_lower: str) -> GuardrailResult:
        """Check for toxic language using a score-based detector."""
        result = self._toxicity_scorer.score(text_lower)
        if result.is_toxic or result.score >= 0.5:
            sanitized = text_lower
            for label in result.labels:
                sanitized = sanitized.replace(label, "*" * len(label))
            return GuardrailResult(
                action=GuardrailAction.WARN
                if result.score < 0.9
                else GuardrailAction.SANITIZE,
                reason="toxicity_detected",
                message=self.REJECTION_MESSAGES["toxicity"],
                triggered_rules=[f"toxicity:{label}" for label in result.labels],
                sanitized_input=sanitized,
                confidence=result.score,
            )

        return GuardrailResult(action=GuardrailAction.ALLOW, reason="no_toxicity")

    def check_output(
        self,
        response: str,
        original_query: str,
        contexts: Optional[List[Dict[str, Any]]] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> GuardrailResult:
        """
        Check AI output for safety and grounding.

        Args:
            response: Generated response to check
            original_query: Original user query for context
            contexts: Optional context documents for grounding check

        Returns:
            GuardrailResult with action
        """
        # 1. Grounding Check (Mencegah Halusinasi)
        if contexts and not self._is_grounded_in(response, contexts):
            return self._apply_policy(
                GuardrailResult(
                    action=GuardrailAction.BLOCK,
                    reason="hallucination_detected",
                    message="Maaf, saya tidak menemukan informasi tersebut di materi kuliah.",
                ),
                context=context,
                surface="output",
            )

        # 2. Pedagogical Alignment: Direct Answer Detection
        if self._contains_direct_answer(response):
            return self._apply_policy(
                GuardrailResult(
                    action=GuardrailAction.REDIRECT,
                    reason="direct_answer_detected",
                    message="Berikan petunjuk Socratic, bukan jawaban langsung.",
                ),
                context=context,
                surface="output",
            )

        # 3. Check if response contains code that might do homework
        if self._contains_complete_solution(response, original_query):
            return self._apply_policy(
                GuardrailResult(
                    action=GuardrailAction.REDIRECT,
                    reason="complete_solution_detected",
                    message="Response contains complete solution, should provide hints instead",
                ),
                context=context,
                surface="output",
            )

        # 4. Check for PII in response
        pii_result = self._check_pii(response)
        if pii_result.action == GuardrailAction.WARN:
            # Sanitize PII from response
            return self._apply_policy(
                GuardrailResult(
                    action=GuardrailAction.SANITIZE,
                    reason="pii_in_response",
                    sanitized_input=self._sanitize_pii(response),
                ),
                context=context,
                surface="output",
            )

        return GuardrailResult(action=GuardrailAction.ALLOW, reason="output_safe")

    def _is_grounded_in(self, response: str, contexts: List[Dict[str, Any]]) -> bool:
        """Heuristic grounding check: check if key technical terms from response exist in context."""
        # Simple keyword overlap check for MVP
        # In production, use a dedicated NLI model or Gemini for grounding
        context_text = " ".join([c.get("content", "").lower() for c in contexts])

        # Extract potential technical words (longer than 5 chars)
        words = re.findall(r"\b\w{6,}\b", response.lower())
        if not words:
            return True

        matches = sum(1 for w in words if w in context_text)
        overlap_ratio = matches / len(words)

        return overlap_ratio > 0.2  # Minimum 20% overlap of technical terms

    def _contains_direct_answer(self, response: str) -> bool:
        """Detect if the bot is giving a direct 'homework-ready' answer."""
        patterns = [
            r"jawabannya adalah",
            r"hasil akhirnya",
            r"berikut adalah kodenya:",
            r"ini jawaban untuk tugas Anda",
        ]
        return any(re.search(p, response, re.IGNORECASE) for p in patterns)

    def _contains_complete_solution(self, response: str, query: str) -> bool:
        """Check if response contains a complete homework solution."""
        # Heuristic: if response contains large code blocks and query was flagged
        query_lower = query.lower()

        # Check if original query was borderline homework request
        homework_indicators = [
            "buatkan kode",
            "write code",
            "buat program",
            "selesaikan",
            "solve",
            "complete",
        ]

        is_homework_query = any(ind in query_lower for ind in homework_indicators)

        if is_homework_query:
            # Check for large code blocks in response
            code_block_pattern = r"```[\s\S]{200,}```"
            if re.search(code_block_pattern, response):
                return True

        return False

    def _sanitize_pii(self, text: str) -> str:
        """Remove PII from text."""
        sanitized = text

        for pattern, pii_type in self._pii_patterns:
            sanitized = pattern.sub(f"[{pii_type}_REDACTED]", sanitized)

        return sanitized


# Singleton instance
_guardrails: Optional[Guardrails] = None


def get_guardrails() -> Guardrails:
    """Get or create guardrails singleton."""
    global _guardrails
    if _guardrails is None:
        _guardrails = Guardrails()
    return _guardrails
