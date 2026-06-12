"""
Tests for Goal Validator Service - 100% Coverage
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.goal_validator import (
    GoalValidator,
    SMARTCriterion,
    SMARTValidationResult,
    get_goal_validator,
)


class TestSMARTCriterion:
    """Test SMARTCriterion enum."""
    
    def test_criterion_values(self):
        """Test enum values."""
        assert SMARTCriterion.SPECIFIC.value == "specific"
        assert SMARTCriterion.MEASURABLE.value == "measurable"
        assert SMARTCriterion.ACHIEVABLE.value == "achievable"
        assert SMARTCriterion.RELEVANT.value == "relevant"
        assert SMARTCriterion.TIME_BOUND.value == "time_bound"


class TestSMARTValidationResult:
    """Test SMARTValidationResult dataclass."""
    
    def test_validation_result_creation(self):
        """Test creating validation result."""
        result = SMARTValidationResult(
            is_valid=True,
            score=1.0,
            feedback="Great goal!",
            missing_criteria=[],
            details={"specific": True, "measurable": True, "time_bound": True},
            suggestions=[]
        )
        
        assert result.is_valid is True
        assert result.score == 1.0
        assert len(result.missing_criteria) == 0
    
    def test_validation_result_invalid(self):
        """Test invalid validation result."""
        result = SMARTValidationResult(
            is_valid=False,
            score=0.33,
            feedback="Missing criteria",
            missing_criteria=["measurable", "time_bound"],
            details={"specific": True, "measurable": False, "time_bound": False},
            suggestions=["Add metrics", "Add deadline"]
        )
        
        assert result.is_valid is False
        assert len(result.missing_criteria) == 2
    
    def test_to_dict(self):
        """Test to_dict conversion."""
        result = SMARTValidationResult(
            is_valid=True,
            score=1.0,
            feedback="Good",
            missing_criteria=[],
            details={"specific": True},
            suggestions=[]
        )
        
        result_dict = result.to_dict()
        
        assert "is_valid" in result_dict
        assert "score" in result_dict
        assert "feedback" in result_dict


class TestGoalValidator:
    """Test GoalValidator class."""
    
    @pytest.fixture
    def validator(self):
        """Create validator instance."""
        return GoalValidator()
    
    def test_init(self, validator):
        """Test initialization."""
        assert validator.OPERATIONAL_VERBS is not None
        assert validator.MEASURABLE_PATTERNS is not None
        assert validator.TIME_BOUND_PATTERNS is not None
        assert validator.GOAL_KEYWORDS is not None
    
    def test_is_goal_statement_true(self, validator):
        """Test is_goal_statement detects goal statements."""
        text = "Saya ingin belajar Python"
        result = validator.is_goal_statement(text)
        assert result is True
    
    def test_is_goal_statement_false(self, validator):
        """Test is_goal_statement with non-goal text."""
        text = "Hari ini cuaca cerah"
        result = validator.is_goal_statement(text)
        assert result is False
    
    def test_is_goal_statement_target(self, validator):
        """Test is_goal_statement with target keyword."""
        text = "Target saya adalah lulus ujian"
        result = validator.is_goal_statement(text)
        assert result is True
    
    def test_check_specific_with_verb(self, validator):
        """Test check_specific with operational verb."""
        text = "Saya ingin membuat aplikasi web"
        result = validator.check_specific(text)
        assert result is True
    
    def test_check_specific_without_verb(self, validator):
        """Test check_specific without operational verb."""
        text = "Saya ingin belajar"
        result = validator.check_specific(text)
        assert result is False
    
    def test_check_specific_various_verbs(self, validator):
        """Test check_specific with various verbs."""
        verbs = [
            "menganalisis", "menerapkan", "mengevaluasi",
            "membuat", "merancang", "mengembangkan",
            "menjelaskan", "mengidentifikasi"
        ]
        
        for verb in verbs:
            text = f"Saya ingin {verb} sesuatu"
            result = validator.check_specific(text)
            assert result is True, f"Failed for verb: {verb}"
    
    def test_check_measurable_with_number(self, validator):
        """Test check_measurable with number."""
        text = "Saya ingin menulis 10 halaman"
        result = validator.check_measurable(text)
        assert result is True
    
    def test_check_measurable_with_percentage(self, validator):
        """Test check_measurable with percentage."""
        text = "Saya ingin mencapai nilai 80%"
        result = validator.check_measurable(text)
        assert result is True
    
    def test_check_measurable_with_units(self, validator):
        """Test check_measurable with units."""
        text = "Saya ingin membuat 5 prototype"
        result = validator.check_measurable(text)
        assert result is True
    
    def test_check_measurable_without_metrics(self, validator):
        """Test check_measurable without metrics."""
        text = "Saya ingin belajar lebih baik"
        result = validator.check_measurable(text)
        assert result is False
    
    def test_check_time_bound_with_deadline(self, validator):
        """Test check_time_bound with deadline."""
        text = "Saya ingin selesai minggu depan"
        result = validator.check_time_bound(text)
        assert result is True
    
    def test_check_time_bound_with_date(self, validator):
        """Test check_time_bound with date."""
        text = "Saya ingin selesai tanggal 15"
        result = validator.check_time_bound(text)
        assert result is True
    
    def test_check_time_bound_without_time(self, validator):
        """Test check_time_bound without time."""
        text = "Saya ingin belajar Python"
        result = validator.check_time_bound(text)
        assert result is False
    
    def test_validate_goal_smart_complete(self, validator):
        """Test validate_goal with complete SMART goal."""
        text = "Saya ingin membuat aplikasi web dengan 5 halaman dalam 2 minggu"
        result = validator.validate_goal(text)
        
        assert result.is_valid is True
        assert result.score == 1.0
        assert len(result.missing_criteria) == 0
    
    def test_validate_goal_missing_criteria(self, validator):
        """Test validate_goal with missing criteria."""
        text = "Saya ingin belajar"
        result = validator.validate_goal(text)
        
        assert result.is_valid is False
        assert result.score < 1.0
        assert len(result.missing_criteria) > 0
    
    def test_validate_goal_specific_only(self, validator):
        """Test validate_goal with only specific criterion."""
        text = "Saya ingin menganalisis data"
        result = validator.validate_goal(text)
        
        assert result.details["specific"] is True
        assert result.details["measurable"] is False
        assert result.details["time_bound"] is False
    
    def test_validate_goal_score_calculation(self, validator):
        """Test validate_goal score calculation."""
        text = "Saya ingin membuat 10 halaman"
        result = validator.validate_goal(text)
        
        # Should have specific and measurable, but no time_bound
        assert result.details["specific"] is True
        assert result.details["measurable"] is True
        assert result.score == 2/3  # 2 out of 3 criteria met
    
    def test_validate_goal_achievable_relevant_implicit(self, validator):
        """Test that achievable and relevant are implicit."""
        text = "Saya ingin belajar"
        result = validator.validate_goal(text)
        
        assert result.details["achievable"] is True
        assert result.details["relevant"] is True
    
    def test_generate_feedback_all_met(self, validator):
        """Test _generate_feedback when all criteria met."""
        details = {
            "specific": True,
            "measurable": True,
            "time_bound": True,
            "achievable": True,
            "relevant": True
        }
        
        feedback, suggestions = validator._generate_feedback(details, [], "Test goal")
        
        assert "SMART" in feedback
        assert len(suggestions) == 0
    
    def test_generate_feedback_missing_specific(self, validator):
        """Test _generate_feedback with missing specific."""
        details = {"specific": False, "measurable": True, "time_bound": True}
        
        feedback, suggestions = validator._generate_feedback(
            details, ["specific"], "Test goal"
        )
        
        assert "SPECIFIC" in feedback
        assert any("SPECIFIC" in s for s in suggestions)
    
    def test_generate_feedback_missing_measurable(self, validator):
        """Test _generate_feedback with missing measurable."""
        details = {"specific": True, "measurable": False, "time_bound": True}
        
        feedback, suggestions = validator._generate_feedback(
            details, ["measurable"], "Test goal"
        )
        
        assert "MEASURABLE" in feedback
        assert any("MEASURABLE" in s for s in suggestions)
    
    def test_generate_feedback_missing_time_bound(self, validator):
        """Test _generate_feedback with missing time_bound."""
        details = {"specific": True, "measurable": True, "time_bound": False}
        
        feedback, suggestions = validator._generate_feedback(
            details, ["time_bound"], "Test goal"
        )
        
        assert "TIME-BOUND" in feedback or "TIME_BOUND" in feedback
        assert any("TIME-BOUND" in s or "TIME_BOUND" in s or "batas waktu" in s for s in suggestions)
    
    def test_generate_feedback_multiple_missing(self, validator):
        """Test _generate_feedback with multiple missing criteria."""
        details = {"specific": False, "measurable": False, "time_bound": False}
        
        feedback, suggestions = validator._generate_feedback(
            details, ["specific", "measurable", "time_bound"], "Test goal"
        )
        
        assert len(suggestions) == 3
    
    def test_get_improvement_hints_all_met(self, validator):
        """Test get_improvement_hints when all criteria met."""
        result = SMARTValidationResult(
            is_valid=True, score=1.0, feedback="Good",
            missing_criteria=[], details={}, suggestions=[]
        )
        
        hints = validator.get_improvement_hints(result)
        
        assert "SMART" in hints
    
    def test_get_improvement_hints_missing_specific(self, validator):
        """Test get_improvement_hints with missing specific."""
        result = SMARTValidationResult(
            is_valid=False, score=0.33, feedback="Missing",
            missing_criteria=["specific"], details={}, suggestions=[]
        )
        
        hints = validator.get_improvement_hints(result)
        
        assert "spesifik" in hints.lower() or "konkret" in hints.lower()
    
    def test_get_improvement_hints_missing_measurable(self, validator):
        """Test get_improvement_hints with missing measurable."""
        result = SMARTValidationResult(
            is_valid=False, score=0.33, feedback="Missing",
            missing_criteria=["measurable"], details={}, suggestions=[]
        )
        
        hints = validator.get_improvement_hints(result)
        
        assert "ukur" in hints.lower() or "target" in hints.lower()
    
    def test_get_improvement_hints_missing_time_bound(self, validator):
        """Test get_improvement_hints with missing time_bound."""
        result = SMARTValidationResult(
            is_valid=False, score=0.33, feedback="Missing",
            missing_criteria=["time_bound"], details={}, suggestions=[]
        )
        
        hints = validator.get_improvement_hints(result)
        
        assert "waktu" in hints.lower() or "batas" in hints.lower()
    
    def test_get_improvement_hints_unknown_criterion(self, validator):
        """Test get_improvement_hints with unknown criterion."""
        result = SMARTValidationResult(
            is_valid=False, score=0.0, feedback="Missing",
            missing_criteria=["unknown"], details={}, suggestions=[]
        )
        
        hints = validator.get_improvement_hints(result)
        
        assert hints is not None
    
    @pytest.mark.asyncio
    async def test_refine_goal(self, validator):
        """Test refine_goal method."""
        import json
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(return_value=MagicMock(
            success=True, content=json.dumps({
                "refined_goal": "Membuat 5 prototype UI dalam 3 hari",
                "explanation": "Ditambahkan target terukur dan batas waktu",
                "suggestions": ["Gunakan Figma", "Buat wireframe dulu"]
            })
        ))
        
        with patch('app.services.llm.get_llm_service', return_value=mock_llm):
            current_goal = "Saya ingin belajar"
            missing_criteria = ["measurable", "time_bound"]
            
            result = await validator.refine_goal(current_goal, missing_criteria)
        
        assert "refined_goal" in result
        assert "success" in result
    
    @pytest.mark.asyncio
    async def test_refine_goal_exception(self, validator):
        """Test refine_goal with exception."""
        current_goal = "Test"
        missing_criteria = ["specific"]
        
        result = await validator.refine_goal(current_goal, missing_criteria)
        
        # Should handle exception gracefully
        assert "success" in result


    @pytest.mark.asyncio
    async def test_refine_goal_plain_json_without_markdown_fence(self, validator):
        import json

        body = json.dumps({"refined_goal": "Menyelesaikan 4 tugas dalam 2 minggu"})
        mock_llm = MagicMock()
        mock_llm.generate = AsyncMock(
            return_value=MagicMock(tokens_used=2, content=body)
        )
        with patch("app.services.llm.get_llm_service", return_value=mock_llm):
            result = await validator.refine_goal("Belajar rutin", ["measurable"])
        assert result["success"] is True


class TestGetGoalValidator:
    """Test get_goal_validator singleton."""
    
    def test_get_goal_validator_singleton(self):
        """Test get_goal_validator returns singleton."""
        from app.services import goal_validator
        goal_validator._goal_validator = None
        
        validator1 = get_goal_validator()
        validator2 = get_goal_validator()
        
        assert validator1 is validator2
        assert isinstance(validator1, GoalValidator)
    
    def test_get_goal_validator_initialization(self):
        """Test get_goal_validator initializes correctly."""
        from app.services import goal_validator
        goal_validator._goal_validator = None
        
        validator = get_goal_validator()
        
        assert validator is not None
        assert isinstance(validator, GoalValidator)
