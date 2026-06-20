"""
Comprehensive Unit Tests for GoalValidator & ChatInterventionService
=====================================================================

Covers:
  GoalValidator:
    - SMART criteria: check_specific, check_measurable, check_time_bound
    - is_goal_statement detection
    - validate_goal result structure and scoring
    - _generate_feedback & get_improvement_hints
    - generate_socratic_hint (random choice mocked)
    - refine_goal (LLM mocked: success, JSON parse error, missing key, exception)
    - get_goal_validator singleton
    - SMARTValidationResult.to_dict()

  ChatInterventionService:
    - Initialization with/without explicit LLM service
    - _check_triggers: inactivity, needs_summary, off_topic, no-trigger path
    - _select_intervention priority logic
    - analyze_and_intervene: empty messages, no-intervention, success, LLM exception
    - generate_summary: success, insufficient messages, LLM exception
    - generate_discussion_prompt: success, with/without context, LLM failure, exception
    - get_intervention_service singleton
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from app.services.goal_validator import (
    GoalValidator,
    SMARTCriterion,
    SMARTValidationResult,
    get_goal_validator,
)
from app.services.intervention import (
    ChatInterventionService,
    InterventionResult,
    InterventionType,
    get_intervention_service,
)
from app.services.llm import LLMResponse

# ============================================================================
# FIXTURES
# ============================================================================

pytestmark = [pytest.mark.unit]


@pytest.fixture
def validator():
    """Fresh GoalValidator for each test."""
    return GoalValidator()


@pytest.fixture
def mock_llm():
    """Pre-configured mock LLM service."""
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value=LLMResponse(
            content="Mock response",
            tokens_used=42,
            model="mock-model",
            success=True,
        )
    )
    llm.generate_intervention = AsyncMock(
        return_value=LLMResponse(
            content="Intervention message",
            tokens_used=50,
            model="mock-model",
            success=True,
        )
    )
    llm.generate_summary = AsyncMock(
        return_value=LLMResponse(
            content="Summary text",
            tokens_used=80,
            model="mock-model",
            success=True,
        )
    )
    llm.model = "mock-model"
    return llm


@pytest.fixture
def intervention_svc(mock_llm):
    """ChatInterventionService with injected mock LLM."""
    return ChatInterventionService(llm_service=mock_llm)


def _make_messages(n, *, base_time=None, content="msg", topic_words=None):
    """Helper to build a list of chat messages."""
    base = base_time or datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    msgs = []
    for i in range(n):
        ts = base + timedelta(minutes=i)
        c = content if topic_words is None else f"{content} {' '.join(topic_words)}"
        msgs.append(
            {"sender": f"user_{i % 3}", "content": c, "timestamp": ts.isoformat()}
        )
    return msgs


# ============================================================================
# GoalValidator  SMART criteria  check_specific
# ============================================================================


class TestCheckSpecific:
    """Operational-verb detection (Bloom's Taxonomy)."""

    @pytest.mark.parametrize(
        "text, expected",
        [
            # Remember level
            ("mengingat rumus kimia", True),
            ("menyebutkan tokoh sejarah", True),
            ("mendefinisikan variabel", True),
            # Understand
            ("menjelaskan konsep OOP", True),
            ("meringkas bab 3", True),
            # Apply
            ("menerapkan algoritma sorting", True),
            ("menggunakan framework Django", True),
            # Analyze
            ("menganalisis data penjualan", True),
            ("membandingkan dua algoritma", True),
            # Evaluate
            ("mengevaluasi performa sistem", True),
            ("menilai kualitas kode", True),
            # Create
            ("membuat dashboard analytics", True),
            ("merancang arsitektur microservice", True),
            ("mendesain UI/UX", True),
            # Additional
            ("menulis unit test", True),
            ("menghitung kompleksitas", True),
            # No verb
            ("belajar React", False),
            ("halo dunia", False),
            ("", False),
        ],
    )
    def test_verb_detection(self, validator, text, expected):
        assert validator.check_specific(text) == expected

    def test_case_insensitive(self, validator):
        assert validator.check_specific("MEMBUAT Aplikasi") is True

    def test_verb_substring_match(self, validator):
        """Verbs are checked via 'in', so substring of word also matches."""
        assert validator.check_specific("xmembuatx") is True


# ============================================================================
# GoalValidator  SMART criteria  check_measurable
# ============================================================================


class TestCheckMeasurable:
    """Numeric / quantifiable metric detection."""

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("membuat 10 halaman", True),  # digit + unit
            ("target 80%", True),  # percentage sign
            ("90 persen akurasi", True),  # word persen
            ("skor minimal 75", True),  # skor + minimal
            ("3 jam coding", True),  # time unit
            ("belajar React", False),
            ("semangat belajar", False),
            ("", False),
        ],
    )
    def test_measurable_patterns(self, validator, text, expected):
        assert validator.check_measurable(text) == expected

    def test_unit_buah(self, validator):
        assert validator.check_measurable("mengerjakan 5 buah soal") is True

    def test_unit_lembar(self, validator):
        assert validator.check_measurable("mencetak 3 lembar") is True

    def test_unit_poin(self, validator):
        assert validator.check_measurable("mendapat 100 poin") is True


# ============================================================================
# GoalValidator  SMART criteria  check_time_bound
# ============================================================================


class TestCheckTimeBound:
    """Deadline / time-period detection."""

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("selesai minggu depan", True),
            ("deadline bulan ini", True),
            ("sebelum tanggal 20", True),
            ("batas waktu senin", True),
            ("besok harus selesai", True),
            ("sampai hari jumat", True),
            ("dalam 2 tahun", True),
            ("selesai 15/01/2025", True),  # date format
            ("segera", False),
            ("nanti", False),  # nanti too vague
            ("", False),
        ],
    )
    def test_time_patterns(self, validator, text, expected):
        assert validator.check_time_bound(text) == expected


# ============================================================================
# GoalValidator  is_goal_statement
# ============================================================================


class TestIsGoalStatement:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("Saya ingin belajar Python", True),
            ("target saya menyelesaikan tugas", True),
            ("tujuan kelompok kami", True),
            ("saya akan belajar", True),
            ("berencana membuat prototype", True),
            ("goal saya adalah lulus", True),
            ("halo semua", False),
            ("apa kabar?", False),
            ("", False),
        ],
    )
    def test_goal_keyword_detection(self, validator, text, expected):
        assert validator.is_goal_statement(text) == expected

    def test_case_insensitive(self, validator):
        assert validator.is_goal_statement("INGIN belajar") is True


# ============================================================================
# GoalValidator  validate_goal  result structure and scoring
# ============================================================================


class TestValidateGoal:
    def test_perfect_smart_goal(self, validator):
        goal = "membuat 5 halaman laporan dalam 3 hari"
        result = validator.validate_goal(goal)

        assert isinstance(result, SMARTValidationResult)
        assert result.is_valid is True
        assert result.score == pytest.approx(1.0)
        assert result.missing_criteria == []
        assert result.details["specific"] is True
        assert result.details["measurable"] is True
        assert result.details["time_bound"] is True
        assert result.details["achievable"] is True
        assert result.details["relevant"] is True

    def test_all_criteria_missing(self, validator):
        result = validator.validate_goal("belajar keras")

        assert result.is_valid is False
        assert result.score == pytest.approx(0.0)
        assert set(result.missing_criteria) == {"specific", "measurable", "time_bound"}

    def test_score_one_of_three(self, validator):
        # Only specific via 'membuat'
        result = validator.validate_goal("membuat laporan")
        assert result.score == pytest.approx(1 / 3)

    def test_score_two_of_three(self, validator):
        # specific + measurable, no time_bound
        result = validator.validate_goal("membuat 5 halaman laporan")
        assert result.score == pytest.approx(2 / 3)

    def test_empty_goal(self, validator):
        result = validator.validate_goal("")
        assert result.is_valid is False
        assert result.score == pytest.approx(0.0)
        assert len(result.missing_criteria) == 3

    def test_to_dict_serialisation(self, validator):
        result = validator.validate_goal("membuat 5 halaman laporan dalam 3 hari")
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "is_valid" in d
        assert "score" in d
        assert "details" in d
        assert "suggestions" in d
        assert "missing_criteria" in d
        assert "feedback" in d


# ============================================================================
# GoalValidator  _generate_feedback
# ============================================================================


class TestGenerateFeedback:
    def test_valid_goal_feedback(self, validator):
        result = validator.validate_goal("membuat 5 halaman laporan minggu depan")
        assert "\u2705" in result.feedback
        assert "SMART" in result.feedback
        assert result.suggestions == []

    def test_missing_specific_suggestion(self, validator):
        result = validator.validate_goal("belajar keras")
        assert "\u26a0\ufe0f" in result.feedback
        assert any("SPECIFIC" in s for s in result.suggestions)

    def test_missing_measurable_suggestion(self, validator):
        result = validator.validate_goal("membuat laporan minggu depan")
        assert any("MEASURABLE" in s for s in result.suggestions)

    def test_missing_time_bound_suggestion(self, validator):
        result = validator.validate_goal("membuat 5 halaman laporan")
        assert any("TIME-BOUND" in s for s in result.suggestions)

    def test_all_missing_suggestions(self, validator):
        result = validator.validate_goal("belajar keras")
        # Should have suggestions for specific, measurable, time_bound
        assert len(result.suggestions) == 3


# ============================================================================
# GoalValidator  get_improvement_hints
# ============================================================================


class TestGetImprovementHints:
    def test_no_missing_criteria(self, validator):
        result = validator.validate_goal("membuat 5 halaman laporan minggu depan")
        hint = validator.get_improvement_hints(result)
        assert "SMART" in hint

    def test_specific_missing_hint(self, validator):
        result = SMARTValidationResult(
            is_valid=False,
            score=0.0,
            feedback="",
            missing_criteria=["specific"],
            details={},
            suggestions=[],
        )
        hint = validator.get_improvement_hints(result)
        assert "spesifik" in hint.lower() or "konkret" in hint.lower()

    def test_measurable_missing_hint(self, validator):
        result = SMARTValidationResult(
            is_valid=False,
            score=0.0,
            feedback="",
            missing_criteria=["measurable"],
            details={},
            suggestions=[],
        )
        hint = validator.get_improvement_hints(result)
        assert "jumlah" in hint.lower() or "berhasil" in hint.lower()

    def test_time_bound_missing_hint(self, validator):
        result = SMARTValidationResult(
            is_valid=False,
            score=0.0,
            feedback="",
            missing_criteria=["time_bound"],
            details={},
            suggestions=[],
        )
        hint = validator.get_improvement_hints(result)
        assert "kapan" in hint.lower() or "waktu" in hint.lower()

    def test_unknown_criterion_fallback(self, validator):
        result = SMARTValidationResult(
            is_valid=False,
            score=0.0,
            feedback="",
            missing_criteria=["unknown_criterion"],
            details={},
            suggestions=[],
        )
        hint = validator.get_improvement_hints(result)
        assert "perjelas" in hint.lower() or "terukur" in hint.lower()


# ============================================================================
# GoalValidator  generate_socratic_hint
# ============================================================================


class TestGenerateSocraticHint:
    def test_no_missing_returns_praise(self, validator):
        hint = validator.generate_socratic_hint([])
        assert "SMART" in hint

    @patch("random.choice", side_effect=lambda lst: lst[0])
    def test_specific_hint(self, _mock_choice, validator):
        hint = validator.generate_socratic_hint(["specific"])
        assert len(hint) > 0
        # first hint from the specific list
        assert "spesifik" in hint.lower() or "topik" in hint.lower()

    @patch("random.choice", side_effect=lambda lst: lst[0])
    def test_measurable_hint(self, _mock_choice, validator):
        hint = validator.generate_socratic_hint(["measurable"])
        assert "indikator" in hint.lower() or "menilai" in hint.lower()

    @patch("random.choice", side_effect=lambda lst: lst[0])
    def test_time_bound_hint(self, _mock_choice, validator):
        hint = validator.generate_socratic_hint(["time_bound"])
        assert "berapa lama" in hint.lower() or "waktu" in hint.lower()

    @patch("random.choice", side_effect=lambda lst: lst[0])
    def test_achievable_hint(self, _mock_choice, validator):
        hint = validator.generate_socratic_hint(["achievable"])
        assert "target" in hint.lower() or "sesi diskusi" in hint.lower()

    @patch("random.choice", side_effect=lambda lst: lst[0])
    def test_multiple_missing_uses_first(self, _mock_choice, validator):
        hint = validator.generate_socratic_hint(["time_bound", "specific"])
        # Should focus on time_bound (first)
        assert "berapa lama" in hint.lower() or "waktu" in hint.lower()

    @patch("random.choice", side_effect=lambda lst: lst[0])
    def test_unknown_criterion_fallback(self, _mock_choice, validator):
        hint = validator.generate_socratic_hint(["nonexistent"])
        assert "kembangkan" in hint.lower() or "mendetail" in hint.lower()


# ============================================================================
# GoalValidator  refine_goal (async, mock LLM)
# ============================================================================


class TestRefineGoal:
    @pytest.mark.asyncio
    async def test_refine_success(self, validator):
        llm_json = json.dumps(
            {
                "refined_goal": "membuat 5 halaman laporan minggu depan",
                "explanation": "Added measurable and time-bound criteria",
                "suggestions": ["Be more specific"],
            }
        )
        mock_response = LLMResponse(
            content=llm_json, tokens_used=100, model="mock", success=True
        )
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=mock_response)

        with patch("app.services.llm.get_llm_service", return_value=mock_llm):
            result = await validator.refine_goal(
                "belajar React", ["specific", "measurable"]
            )

        assert result["success"] is True
        assert "refined_goal" in result
        assert "explanation" in result
        assert "suggestions" in result
        assert "validation" in result
        assert result["tokens_used"] == 100

    @pytest.mark.asyncio
    async def test_refine_json_in_code_block(self, validator):
        """LLM wraps JSON in ```json ... ```."""
        raw = (
            '```json\n{"refined_goal": "membuat 10 halaman", "explanation": "ok"}\n```'
        )
        mock_response = LLMResponse(
            content=raw, tokens_used=50, model="mock", success=True
        )
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=mock_response)

        with patch("app.services.llm.get_llm_service", return_value=mock_llm):
            result = await validator.refine_goal("belajar", ["specific"])

        assert result["success"] is True
        assert result["refined_goal"] == "membuat 10 halaman"

    @pytest.mark.asyncio
    async def test_refine_alternative_key_goal(self, validator):
        """LLM uses 'goal' instead of 'refined_goal'."""
        llm_json = json.dumps({"goal": "membuat 5 halaman", "explanation": "ok"})
        mock_response = LLMResponse(
            content=llm_json, tokens_used=50, model="mock", success=True
        )
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=mock_response)

        with patch("app.services.llm.get_llm_service", return_value=mock_llm):
            result = await validator.refine_goal("belajar", ["specific"])

        assert result["success"] is True
        assert result["refined_goal"] == "membuat 5 halaman"

    @pytest.mark.asyncio
    async def test_refine_alternative_key_improved_goal(self, validator):
        """LLM uses 'improved_goal' instead of 'refined_goal'."""
        llm_json = json.dumps(
            {"improved_goal": "membuat 5 halaman", "explanation": "ok"}
        )
        mock_response = LLMResponse(
            content=llm_json, tokens_used=50, model="mock", success=True
        )
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=mock_response)

        with patch("app.services.llm.get_llm_service", return_value=mock_llm):
            result = await validator.refine_goal("belajar", ["specific"])

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_refine_missing_all_keys_raises(self, validator):
        """JSON has none of the expected keys -> returns success=False."""
        llm_json = json.dumps({"random_key": "value"})
        mock_response = LLMResponse(
            content=llm_json, tokens_used=50, model="mock", success=True
        )
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=mock_response)

        with patch("app.services.llm.get_llm_service", return_value=mock_llm):
            result = await validator.refine_goal("belajar", ["specific"])

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_refine_json_parse_failure(self, validator):
        """LLM returns non-JSON text."""
        mock_response = LLMResponse(
            content="This is not JSON at all",
            tokens_used=50,
            model="mock",
            success=True,
        )
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=mock_response)

        with patch("app.services.llm.get_llm_service", return_value=mock_llm):
            result = await validator.refine_goal("belajar", ["specific"])

        assert result["success"] is False
        assert "raw_response" in result

    @pytest.mark.asyncio
    async def test_refine_llm_exception(self, validator):
        """LLM raises an exception."""
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(side_effect=RuntimeError("API down"))

        with patch("app.services.llm.get_llm_service", return_value=mock_llm):
            result = await validator.refine_goal("belajar", ["specific"])

        assert result["success"] is False
        assert result["error"] == "Internal error"

    @pytest.mark.asyncio
    async def test_refine_refined_goal_not_string(self, validator):
        """LLM returns refined_goal as non-string -> TypeError caught."""
        llm_json = json.dumps({"refined_goal": 12345, "explanation": "ok"})
        mock_response = LLMResponse(
            content=llm_json, tokens_used=50, model="mock", success=True
        )
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=mock_response)

        with patch("app.services.llm.get_llm_service", return_value=mock_llm):
            result = await validator.refine_goal("belajar", ["specific"])

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_refine_criteria_explanations_mapping(self, validator):
        """Ensure all three criteria mappings are used in the prompt."""
        mock_response = LLMResponse(
            content=json.dumps({"refined_goal": "membuat 5 halaman minggu depan"}),
            tokens_used=50,
            model="mock",
            success=True,
        )
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=mock_response)

        with patch("app.services.llm.get_llm_service", return_value=mock_llm):
            await validator.refine_goal(
                "belajar",
                ["specific", "measurable", "time_bound"],
            )

        call_kwargs = mock_llm.generate.call_args[1]
        prompt_text = call_kwargs["prompt"]
        assert "specific" in prompt_text
        assert "measurable" in prompt_text
        assert "time_bound" in prompt_text


# ============================================================================
# GoalValidator  singleton
# ============================================================================


class TestGoalValidatorSingleton:
    def test_get_goal_validator_returns_same_instance(self):
        import app.services.goal_validator as gv_mod

        gv_mod._goal_validator = None  # reset
        v1 = get_goal_validator()
        v2 = get_goal_validator()
        assert v1 is v2
        gv_mod._goal_validator = None  # cleanup


# ============================================================================
# SMARTValidationResult  dataclass
# ============================================================================


class TestSMARTValidationResult:
    def test_fields(self):
        r = SMARTValidationResult(
            is_valid=True,
            score=0.8,
            feedback="ok",
            missing_criteria=["specific"],
            details={"specific": False},
            suggestions=["tip1"],
        )
        assert r.is_valid is True
        assert r.score == 0.8
        assert r.missing_criteria == ["specific"]

    def test_to_dict_matches_asdict(self):
        r = SMARTValidationResult(
            is_valid=False,
            score=0.5,
            feedback="fb",
            missing_criteria=[],
            details={},
            suggestions=[],
        )
        assert r.to_dict() == asdict(r)


# ============================================================================
# SMARTCriterion enum
# ============================================================================


class TestSMARTCriterion:
    def test_values(self):
        assert SMARTCriterion.SPECIFIC.value == "specific"
        assert SMARTCriterion.MEASURABLE.value == "measurable"
        assert SMARTCriterion.ACHIEVABLE.value == "achievable"
        assert SMARTCriterion.RELEVANT.value == "relevant"
        assert SMARTCriterion.TIME_BOUND.value == "time_bound"

    def test_is_str_subclass(self):
        assert isinstance(SMARTCriterion.SPECIFIC, str)


# ============================================================================
# ChatInterventionService  initialization
# ============================================================================


class TestInterventionInit:
    def test_constants(self, intervention_svc):
        assert intervention_svc.off_topic_threshold == 0.6
        assert intervention_svc.inactivity_threshold_minutes == 30
        assert intervention_svc.minimum_messages_for_summary == 10

    def test_injected_llm(self, mock_llm, intervention_svc):
        assert intervention_svc.llm_service is mock_llm

    def test_default_llm_via_get_llm_service(self):
        with patch("app.services.intervention.get_llm_service") as mock_get:
            mock_get.return_value = MagicMock()
            svc = ChatInterventionService()
            assert svc.llm_service is mock_get.return_value


# ============================================================================
# ChatInterventionService  _check_triggers
# ============================================================================


class TestCheckTriggers:
    @pytest.mark.asyncio
    async def test_inactivity_trigger(self, intervention_svc):
        old_time = datetime.now(timezone.utc) - timedelta(minutes=60)
        messages = [{"content": "hi", "timestamp": old_time.isoformat()}]

        triggers = await intervention_svc._check_triggers(messages, "topic", None)

        assert triggers["inactive"] is True
        assert triggers["should_intervene"] is True

    @pytest.mark.asyncio
    async def test_no_inactivity_recent_message(self, intervention_svc):
        recent = datetime.now(timezone.utc) - timedelta(minutes=5)
        messages = [{"content": "hi", "timestamp": recent.isoformat()}]

        triggers = await intervention_svc._check_triggers(messages, "topic", None)

        assert triggers["inactive"] is False

    @pytest.mark.asyncio
    async def test_no_timestamp_no_inactivity(self, intervention_svc):
        messages = [{"content": "hi"}]

        triggers = await intervention_svc._check_triggers(messages, "topic", None)

        assert triggers["inactive"] is False

    @pytest.mark.asyncio
    async def test_timestamp_as_string_with_z(self, intervention_svc):
        old = datetime.now(timezone.utc) - timedelta(minutes=45)
        ts = old.strftime("%Y-%m-%dT%H:%M:%SZ")
        messages = [{"content": "hi", "timestamp": ts}]

        triggers = await intervention_svc._check_triggers(messages, "topic", None)

        assert triggers["inactive"] is True

    @pytest.mark.asyncio
    async def test_needs_summary_trigger(self, intervention_svc):
        """When >=10 messages arrived since last intervention, needs_summary = True."""
        last_intervention = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        messages = _make_messages(
            12,
            base_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        )

        triggers = await intervention_svc._check_triggers(
            messages, "topic", last_intervention
        )

        assert triggers["needs_summary"] is True

    @pytest.mark.asyncio
    async def test_needs_summary_not_enough_messages(self, intervention_svc):
        last_intervention = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        messages = _make_messages(
            5,
            base_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        )

        triggers = await intervention_svc._check_triggers(
            messages, "topic", last_intervention
        )

        assert triggers["needs_summary"] is False

    @pytest.mark.asyncio
    async def test_needs_summary_no_last_intervention(self, intervention_svc):
        """No last_intervention_time -> needs_summary stays False even with enough msgs."""
        messages = _make_messages(15)

        triggers = await intervention_svc._check_triggers(messages, "topic", None)

        assert triggers["needs_summary"] is False

    @pytest.mark.asyncio
    async def test_needs_summary_not_enough_since_intervention(self, intervention_svc):
        """Enough total messages but not enough since last intervention."""
        base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        messages = _make_messages(12, base_time=base)
        # Last intervention was after most messages
        last_intervention = base + timedelta(minutes=8)

        triggers = await intervention_svc._check_triggers(
            messages, "topic", last_intervention
        )

        assert triggers["needs_summary"] is False

    @pytest.mark.asyncio
    async def test_off_topic_trigger(self, intervention_svc):
        """Messages that don't mention the topic words at all."""
        messages = _make_messages(6, content="talking about football and games")

        triggers = await intervention_svc._check_triggers(
            messages, "database normalization", None
        )

        assert triggers["off_topic"] is True
        assert triggers["should_intervene"] is True
        assert triggers["off_topic_score"] > 0

    @pytest.mark.asyncio
    async def test_on_topic_no_trigger(self, intervention_svc):
        """Messages that mention the topic words -> no off-topic."""
        messages = _make_messages(
            6,
            content="discussing database normalization techniques",
        )

        triggers = await intervention_svc._check_triggers(
            messages, "database normalization", None
        )

        assert triggers["off_topic"] is False

    @pytest.mark.asyncio
    async def test_off_topic_skipped_less_than_5_messages(self, intervention_svc):
        messages = _make_messages(3, content="football")

        triggers = await intervention_svc._check_triggers(
            messages, "database normalization", None
        )

        assert triggers["off_topic"] is False

    @pytest.mark.asyncio
    async def test_off_topic_empty_topic(self, intervention_svc):
        messages = _make_messages(6, content="football")

        triggers = await intervention_svc._check_triggers(messages, "", None)

        assert triggers["off_topic"] is False

    @pytest.mark.asyncio
    async def test_no_triggers_at_all(self, intervention_svc):
        recent = datetime.now(timezone.utc) - timedelta(minutes=2)
        messages = [{"content": "hi", "timestamp": recent.isoformat()}]

        triggers = await intervention_svc._check_triggers(messages, "", None)

        assert triggers["should_intervene"] is False
        assert triggers["inactive"] is False
        assert triggers["off_topic"] is False
        assert triggers["needs_summary"] is False


# ============================================================================
# ChatInterventionService  _select_intervention
# ============================================================================


class TestSelectIntervention:
    def test_off_topic_priority(self, intervention_svc):
        triggers = {"off_topic": True, "off_topic_score": 0.9, "inactive": True}
        itype, conf, reason = intervention_svc._select_intervention(triggers)
        assert itype == InterventionType.REDIRECT
        assert conf == 0.9
        assert "off-topic" in reason.lower()

    def test_inactive_priority(self, intervention_svc):
        triggers = {"off_topic": False, "inactive": True, "needs_summary": True}
        itype, conf, reason = intervention_svc._select_intervention(triggers)
        assert itype == InterventionType.ENCOURAGE
        assert conf == 0.8

    def test_needs_summary_priority(self, intervention_svc):
        triggers = {"off_topic": False, "inactive": False, "needs_summary": True}
        itype, conf, reason = intervention_svc._select_intervention(triggers)
        assert itype == InterventionType.SUMMARIZE
        assert conf == 0.7

    def test_low_engagement(self, intervention_svc):
        triggers = {
            "off_topic": False,
            "inactive": False,
            "needs_summary": False,
            "low_engagement": True,
        }
        itype, conf, reason = intervention_svc._select_intervention(triggers)
        assert itype == InterventionType.PROMPT
        assert conf == 0.6

    def test_no_trigger(self, intervention_svc):
        triggers = {
            "off_topic": False,
            "inactive": False,
            "needs_summary": False,
            "low_engagement": False,
        }
        itype, conf, reason = intervention_svc._select_intervention(triggers)
        assert itype == InterventionType.ENCOURAGE
        assert conf == 0.0
        assert "no intervention" in reason.lower()

    def test_off_topic_score_default(self, intervention_svc):
        triggers = {"off_topic": True}  # no off_topic_score
        itype, conf, _ = intervention_svc._select_intervention(triggers)
        assert itype == InterventionType.REDIRECT
        assert conf == 0.5  # default


# ============================================================================
# ChatInterventionService  analyze_and_intervene
# ============================================================================


class TestAnalyzeAndIntervene:
    @pytest.mark.asyncio
    async def test_empty_messages(self, intervention_svc):
        result = await intervention_svc.analyze_and_intervene(
            messages=[], topic="test", chat_room_id="room1"
        )
        assert isinstance(result, InterventionResult)
        assert result.should_intervene is False
        assert result.intervention_type == InterventionType.ENCOURAGE
        assert result.success is True
        assert result.message == ""

    @pytest.mark.asyncio
    async def test_no_intervention_needed(self, intervention_svc):
        recent = datetime.now(timezone.utc) - timedelta(minutes=2)
        messages = [{"content": "hi", "timestamp": recent.isoformat()}]

        result = await intervention_svc.analyze_and_intervene(
            messages=messages, topic="", chat_room_id="room1"
        )

        assert result.should_intervene is False
        assert result.success is True

    @pytest.mark.asyncio
    async def test_intervention_generated_on_inactivity(
        self, intervention_svc, mock_llm
    ):
        old = datetime.now(timezone.utc) - timedelta(minutes=60)
        messages = [{"content": "hi", "timestamp": old.isoformat()}]

        result = await intervention_svc.analyze_and_intervene(
            messages=messages, topic="test", chat_room_id="room1"
        )

        assert result.should_intervene is True
        assert result.success is True
        assert result.message == "Intervention message"
        mock_llm.generate_intervention.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_intervention_on_off_topic(self, intervention_svc, mock_llm):
        recent = datetime.now(timezone.utc) - timedelta(minutes=1)
        messages = [
            {
                "content": "let's play football",
                "timestamp": (recent + timedelta(seconds=i)).isoformat(),
            }
            for i in range(6)
        ]

        result = await intervention_svc.analyze_and_intervene(
            messages=messages, topic="database normalization", chat_room_id="room1"
        )

        assert result.should_intervene is True
        assert result.intervention_type == InterventionType.REDIRECT

    @pytest.mark.asyncio
    async def test_llm_exception_during_generation(self, intervention_svc, mock_llm):
        old = datetime.now(timezone.utc) - timedelta(minutes=60)
        messages = [{"content": "hi", "timestamp": old.isoformat()}]

        mock_llm.generate_intervention = AsyncMock(
            side_effect=RuntimeError("LLM exploded")
        )

        result = await intervention_svc.analyze_and_intervene(
            messages=messages, topic="test", chat_room_id="room1"
        )

        assert result.should_intervene is False
        assert result.success is False
        assert result.error == "Internal error"

    @pytest.mark.asyncio
    async def test_llm_response_fields_propagated(self, intervention_svc, mock_llm):
        old = datetime.now(timezone.utc) - timedelta(minutes=60)
        messages = [{"content": "hi", "timestamp": old.isoformat()}]

        mock_llm.generate_intervention = AsyncMock(
            return_value=LLMResponse(
                content="Go back to topic",
                tokens_used=30,
                model="test",
                success=True,
                error=None,
            )
        )

        result = await intervention_svc.analyze_and_intervene(
            messages=messages, topic="test", chat_room_id="room1"
        )

        assert result.message == "Go back to topic"
        assert result.success is True
        assert result.error is None


# ============================================================================
# ChatInterventionService  generate_summary
# ============================================================================


class TestGenerateSummary:
    @pytest.mark.asyncio
    async def test_success(self, intervention_svc, mock_llm):
        messages = _make_messages(12)
        result = await intervention_svc.generate_summary(messages, "room1")

        assert result.success is True
        assert result.should_intervene is True
        assert result.intervention_type == InterventionType.SUMMARIZE
        assert result.message == "Summary text"
        mock_llm.generate_summary.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_insufficient_messages(self, intervention_svc):
        messages = _make_messages(5)
        result = await intervention_svc.generate_summary(messages, "room1")

        assert result.success is True
        assert result.should_intervene is False
        assert "10" in result.reason
        assert "Belum cukup" in result.message

    @pytest.mark.asyncio
    async def test_exactly_threshold_messages(self, intervention_svc, mock_llm):
        messages = _make_messages(10)
        result = await intervention_svc.generate_summary(messages, "room1")

        assert result.should_intervene is True
        mock_llm.generate_summary.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_llm_exception(self, intervention_svc, mock_llm):
        messages = _make_messages(12)
        mock_llm.generate_summary = AsyncMock(side_effect=RuntimeError("boom"))

        result = await intervention_svc.generate_summary(messages, "room1")

        assert result.success is False
        assert result.should_intervene is False
        assert result.error == "Internal error"

    @pytest.mark.asyncio
    async def test_llm_returns_error_response(self, intervention_svc, mock_llm):
        messages = _make_messages(12)
        mock_llm.generate_summary = AsyncMock(
            return_value=LLMResponse(
                content="",
                tokens_used=0,
                model="mock",
                success=False,
                error="rate limited",
            )
        )

        result = await intervention_svc.generate_summary(messages, "room1")

        assert result.success is False
        assert result.should_intervene is True
        assert result.error == "rate limited"


# ============================================================================
# ChatInterventionService  generate_discussion_prompt
# ============================================================================


class TestGenerateDiscussionPrompt:
    @pytest.mark.asyncio
    async def test_basic_prompt(self, intervention_svc, mock_llm):
        result = await intervention_svc.generate_discussion_prompt(topic="AI Ethics")

        assert result.success is True
        assert result.should_intervene is True
        assert result.intervention_type == InterventionType.PROMPT
        call_kwargs = mock_llm.generate.call_args[1]
        assert "AI Ethics" in call_kwargs["prompt"]
        assert "medium" in call_kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_with_context_and_difficulty(self, intervention_svc, mock_llm):
        result = await intervention_svc.generate_discussion_prompt(
            topic="ML", context="Students learning CNNs", difficulty="hard"
        )

        assert result.success is True
        call_kwargs = mock_llm.generate.call_args[1]
        assert "hard" in call_kwargs["prompt"]
        assert "Students learning CNNs" in call_kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_without_context(self, intervention_svc, mock_llm):
        result = await intervention_svc.generate_discussion_prompt(topic="NLP")

        assert result.success is True
        call_kwargs = mock_llm.generate.call_args[1]
        assert "Konteks tambahan" not in call_kwargs["prompt"]

    @pytest.mark.asyncio
    async def test_llm_failure_response(self, intervention_svc, mock_llm):
        mock_llm.generate = AsyncMock(
            return_value=LLMResponse(
                content="",
                tokens_used=0,
                model="mock",
                success=False,
                error="Service unavailable",
            )
        )

        result = await intervention_svc.generate_discussion_prompt(topic="Test")

        assert result.success is False
        assert result.should_intervene is False
        assert "Service unavailable" in result.reason

    @pytest.mark.asyncio
    async def test_llm_exception(self, intervention_svc, mock_llm):
        mock_llm.generate = AsyncMock(side_effect=ConnectionError("timeout"))

        result = await intervention_svc.generate_discussion_prompt(topic="Test")

        assert result.success is False
        assert result.should_intervene is False
        assert result.error == "Internal error"

    @pytest.mark.asyncio
    async def test_system_prompt_passed(self, intervention_svc, mock_llm):
        await intervention_svc.generate_discussion_prompt(topic="Testing")

        call_kwargs = mock_llm.generate.call_args[1]
        assert "fasilitator" in call_kwargs["system_prompt"].lower()

    @pytest.mark.asyncio
    async def test_temperature_08(self, intervention_svc, mock_llm):
        await intervention_svc.generate_discussion_prompt(topic="Testing")

        call_kwargs = mock_llm.generate.call_args[1]
        assert call_kwargs["temperature"] == 0.8


# ============================================================================
# ChatInterventionService  singleton
# ============================================================================


class TestInterventionSingleton:
    def test_get_intervention_service_returns_same(self):
        import app.services.intervention as iv_mod

        iv_mod._intervention_service = None
        with patch("app.services.intervention.get_llm_service") as mock_get:
            mock_get.return_value = MagicMock()
            s1 = get_intervention_service()
            s2 = get_intervention_service()
            assert s1 is s2
        iv_mod._intervention_service = None


# ============================================================================
# InterventionType enum
# ============================================================================


class TestInterventionType:
    def test_values(self):
        assert InterventionType.REDIRECT.value == "redirect"
        assert InterventionType.PROMPT.value == "prompt"
        assert InterventionType.SUMMARIZE.value == "summarize"
        assert InterventionType.CLARIFY.value == "clarify"
        assert InterventionType.RESOURCE.value == "resource"
        assert InterventionType.ENCOURAGE.value == "encourage"

    def test_is_str_subclass(self):
        assert isinstance(InterventionType.REDIRECT, str)


# ============================================================================
# InterventionResult dataclass
# ============================================================================


class TestInterventionResult:
    def test_required_fields(self):
        r = InterventionResult(
            message="msg",
            intervention_type=InterventionType.PROMPT,
            confidence=0.9,
            should_intervene=True,
            reason="testing",
            success=True,
        )
        assert r.error is None
        assert r.message == "msg"

    def test_optional_error(self):
        r = InterventionResult(
            message="",
            intervention_type=InterventionType.REDIRECT,
            confidence=0.5,
            should_intervene=False,
            reason="fail",
            success=False,
            error="bad request",
        )
        assert r.error == "bad request"


# ============================================================================
# Edge cases & integration between validator + intervention
# ============================================================================


class TestEdgeCases:
    def test_validate_goal_special_chars(self, validator):
        result = validator.validate_goal("membuat 5 laporan! @#$% minggu")
        assert result is not None
        assert isinstance(result.is_valid, bool)

    def test_validate_very_long_goal(self, validator):
        long = "membuat " * 500 + "5 halaman minggu depan"
        result = validator.validate_goal(long)
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_analyze_with_datetime_objects(self, intervention_svc):
        """Timestamps can be datetime objects, not just strings."""
        old = datetime.now(timezone.utc) - timedelta(minutes=60)
        messages = [{"content": "hi", "timestamp": old}]

        result = await intervention_svc.analyze_and_intervene(
            messages=messages, topic="test", chat_room_id="room1"
        )

        # Should handle datetime object directly without crash
        assert result.should_intervene is True

    @pytest.mark.asyncio
    async def test_analyze_last_intervention_time(self, intervention_svc, mock_llm):
        """Passing last_intervention_time affects needs_summary check."""
        base = datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        messages = _make_messages(12, base_time=base)
        last_int = base - timedelta(hours=1)

        result = await intervention_svc.analyze_and_intervene(
            messages=messages,
            topic="database normalization",
            chat_room_id="room1",
            last_intervention_time=last_int,
        )

        assert isinstance(result, InterventionResult)
