"""Tests for chat intervention service."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import intervention
from app.services.intervention import (
    ChatInterventionService,
    InterventionResult,
    InterventionType,
    get_intervention_service,
)
from app.services.llm import LLMResponse


class TestInterventionResult:
    def test_intervention_result_success(self):
        result = InterventionResult(
            message="Test message",
            intervention_type=InterventionType.REDIRECT,
            confidence=0.85,
            should_intervene=True,
            reason="Off-topic detected",
            success=True,
        )

        assert result.message == "Test message"
        assert result.should_intervene is True
        assert result.error is None

    def test_intervention_result_with_error(self):
        result = InterventionResult(
            message="",
            intervention_type=InterventionType.PROMPT,
            confidence=0.0,
            should_intervene=False,
            reason="Error occurred",
            success=False,
            error="Test error",
        )

        assert result.success is False
        assert result.error == "Test error"


class TestInterventionType:
    def test_intervention_type_values(self):
        assert InterventionType.REDIRECT.value == "redirect"
        assert InterventionType.PROMPT.value == "prompt"
        assert InterventionType.SUMMARIZE.value == "summarize"
        assert InterventionType.CLARIFY.value == "clarify"
        assert InterventionType.RESOURCE.value == "resource"
        assert InterventionType.ENCOURAGE.value == "encourage"


@pytest.fixture
def mock_llm():
    mock = MagicMock()
    mock.generate = AsyncMock(
        return_value=LLMResponse(
            content="Prompt response",
            tokens_used=50,
            model="mock-model",
            success=True,
        )
    )
    mock.generate_intervention = AsyncMock(
        return_value=LLMResponse(
            content="Intervention response",
            tokens_used=60,
            model="mock-model",
            success=True,
        )
    )
    mock.generate_summary = AsyncMock(
        return_value=LLMResponse(
            content="Summary response",
            tokens_used=70,
            model="mock-model",
            success=True,
        )
    )
    return mock


@pytest.fixture
def intervention_service(mock_llm):
    return ChatInterventionService(llm_service=mock_llm)


class TestChatInterventionService:
    @pytest.mark.asyncio
    async def test_analyze_and_intervene_no_messages(self, intervention_service):
        result = await intervention_service.analyze_and_intervene(
            messages=[],
            topic="Test topic",
            chat_room_id="room_1",
        )

        assert result.success is True
        assert result.should_intervene is False
        assert result.reason == "No messages to analyze"

    @pytest.mark.asyncio
    async def test_analyze_and_intervene_no_trigger(self, intervention_service, mock_llm):
        messages = [
            {"sender": "User1", "content": "Test topic ini menarik"},
            {"sender": "User2", "content": "Saya setuju topik ini penting"},
        ]

        result = await intervention_service.analyze_and_intervene(
            messages=messages,
            topic="Test topic",
            chat_room_id="room_1",
        )

        assert result.success is True
        assert result.should_intervene is False
        mock_llm.generate_intervention.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_analyze_and_intervene_off_topic_generates_message(self, intervention_service, mock_llm):
        messages = [
            {"sender": "User1", "content": "Kami membahas film dan kopi"},
            {"sender": "User2", "content": "Bukan soal akademik sama sekali"},
            {"sender": "User3", "content": "Besok nonton dimana?"},
            {"sender": "User1", "content": "Saya suka stadion"},
            {"sender": "User2", "content": "Musik juga seru"},
        ]

        result = await intervention_service.analyze_and_intervene(
            messages=messages,
            topic="Machine Learning",
            chat_room_id="room_1",
        )

        assert result.success is True
        assert result.should_intervene is True
        assert result.intervention_type == InterventionType.REDIRECT
        assert result.message == "Intervention response"
        mock_llm.generate_intervention.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_analyze_and_intervene_generation_failure(self, intervention_service, mock_llm):
        mock_llm.generate_intervention.side_effect = Exception("boom")
        messages = [
            {"sender": "User1", "content": "Kami membahas film dan kopi"},
            {"sender": "User2", "content": "Bukan soal akademik sama sekali"},
            {"sender": "User3", "content": "Besok nonton dimana?"},
            {"sender": "User1", "content": "Saya suka stadion"},
            {"sender": "User2", "content": "Musik juga seru"},
        ]

        result = await intervention_service.analyze_and_intervene(
            messages=messages,
            topic="Machine Learning",
            chat_room_id="room_1",
        )

        assert result.success is False
        assert result.should_intervene is False
        assert "Generation failed" in result.reason
        assert result.error == "Internal error"

    @pytest.mark.asyncio
    async def test_check_triggers_detects_inactivity(self, intervention_service):
        stale_time = datetime.now() - timedelta(minutes=45)
        messages = [{"sender": "User1", "content": "Hello", "timestamp": stale_time}]

        triggers = await intervention_service._check_triggers(
            messages=messages,
            topic="Test topic",
            last_intervention_time=None,
        )

        assert triggers["inactive"] is True
        assert triggers["should_intervene"] is True

    @pytest.mark.asyncio
    async def test_check_triggers_detects_summary_need(self, intervention_service):
        now = datetime.now()
        last_intervention_time = now - timedelta(minutes=20)
        messages = [
            {"sender": f"User{i}", "content": f"Pesan {i}", "timestamp": now.isoformat()}
            for i in range(10)
        ]

        triggers = await intervention_service._check_triggers(
            messages=messages,
            topic="Topik diskusi",
            last_intervention_time=last_intervention_time,
        )

        assert triggers["needs_summary"] is True

    @pytest.mark.asyncio
    async def test_check_triggers_detects_off_topic(self, intervention_service):
        messages = [
            {"sender": "User1", "content": "film kopi musik stadion"},
            {"sender": "User2", "content": "liburan konser hujan jalan"},
            {"sender": "User3", "content": "pantai game makanan kamera"},
            {"sender": "User4", "content": "cuaca tiket motor basket"},
            {"sender": "User5", "content": "nonton laptop meja sepatu"},
        ]

        triggers = await intervention_service._check_triggers(
            messages=messages,
            topic="Machine Learning",
            last_intervention_time=None,
        )

        assert triggers["off_topic"] is True
        assert triggers["should_intervene"] is True
        assert triggers["off_topic_score"] > 0.6

    def test_select_intervention(self, intervention_service):
        intervention_type, confidence, reason = intervention_service._select_intervention(
            {
                "off_topic": True,
                "off_topic_score": 0.9,
                "inactive": False,
                "needs_summary": False,
                "low_engagement": False,
            }
        )

        assert intervention_type == InterventionType.REDIRECT
        assert confidence == 0.9
        assert "off-topic" in reason.lower()

    def test_select_intervention_no_triggers(self, intervention_service):
        intervention_type, confidence, reason = intervention_service._select_intervention(
            {
                "off_topic": False,
                "inactive": False,
                "needs_summary": False,
                "low_engagement": False,
            }
        )

        assert intervention_type == InterventionType.ENCOURAGE
        assert confidence == 0.0
        assert reason == "No intervention needed"

    def test_select_intervention_multiple_triggers_prioritizes_off_topic(self, intervention_service):
        intervention_type, confidence, reason = intervention_service._select_intervention(
            {
                "off_topic": True,
                "off_topic_score": 0.75,
                "inactive": True,
                "needs_summary": True,
                "low_engagement": True,
            }
        )

        assert intervention_type == InterventionType.REDIRECT
        assert confidence == 0.75
        assert "off-topic" in reason.lower()

    @pytest.mark.asyncio
    async def test_generate_summary_not_enough_messages(self, intervention_service):
        result = await intervention_service.generate_summary(
            messages=[{"sender": "User1", "content": "Short"}],
            chat_room_id="room_1",
        )

        assert result.success is True
        assert result.should_intervene is False
        assert "Belum cukup pesan" in result.message

    @pytest.mark.asyncio
    async def test_generate_summary_success(self, intervention_service, mock_llm):
        messages = [{"sender": f"User{i}", "content": f"Pesan {i}"} for i in range(10)]

        result = await intervention_service.generate_summary(messages=messages, chat_room_id="room_1")

        assert result.success is True
        assert result.should_intervene is True
        assert result.intervention_type == InterventionType.SUMMARIZE
        assert result.message == "Summary response"
        mock_llm.generate_summary.assert_awaited_once_with(messages=messages, include_action_items=True)

    @pytest.mark.asyncio
    async def test_generate_summary_failure(self, intervention_service, mock_llm):
        mock_llm.generate_summary.side_effect = Exception("summary boom")
        messages = [{"sender": f"User{i}", "content": f"Pesan {i}"} for i in range(10)]

        result = await intervention_service.generate_summary(messages=messages, chat_room_id="room_1")

        assert result.success is False
        assert result.should_intervene is False
        assert result.error == "Internal error"

    @pytest.mark.asyncio
    async def test_generate_discussion_prompt_success(self, intervention_service, mock_llm):
        result = await intervention_service.generate_discussion_prompt(
            topic="AI Ethics",
            context="Fokus pada dampak sosial",
            difficulty="hard",
        )

        assert result.success is True
        assert result.should_intervene is True
        assert result.intervention_type == InterventionType.PROMPT
        assert result.message == "Prompt response"
        mock_llm.generate.assert_awaited_once()
        called_prompt = mock_llm.generate.await_args.kwargs["prompt"]
        assert "AI Ethics" in called_prompt
        assert "Fokus pada dampak sosial" in called_prompt
        assert "hard" in called_prompt

    @pytest.mark.asyncio
    async def test_generate_discussion_prompt_unsuccessful_llm_response(self, intervention_service, mock_llm):
        mock_llm.generate.return_value = LLMResponse(
            content="",
            tokens_used=0,
            model="mock-model",
            success=False,
            error="llm failed",
        )

        result = await intervention_service.generate_discussion_prompt(topic="AI Ethics")

        assert result.success is False
        assert result.should_intervene is False
        assert result.error == "llm failed"

    @pytest.mark.asyncio
    async def test_generate_discussion_prompt_exception(self, intervention_service, mock_llm):
        mock_llm.generate.side_effect = Exception("prompt boom")

        result = await intervention_service.generate_discussion_prompt(topic="AI Ethics")

        assert result.success is False
        assert result.should_intervene is False
        assert result.error == "Internal error"


class TestGetInterventionService:
    def test_get_intervention_service_singleton(self):
        intervention._intervention_service = None

        with patch("app.services.intervention.get_llm_service", return_value=MagicMock()):
            service1 = get_intervention_service()
            service2 = get_intervention_service()

        assert service1 is service2
        assert isinstance(service1, ChatInterventionService)

    def test_get_intervention_service_uses_get_llm_service(self):
        intervention._intervention_service = None
        mock_service = MagicMock()

        with patch("app.services.intervention.get_llm_service", return_value=mock_service):
            service = get_intervention_service()

        assert service.llm_service is mock_service
