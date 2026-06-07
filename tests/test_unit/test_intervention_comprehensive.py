"""Comprehensive tests for the current intervention service API."""

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


@pytest.fixture
def mock_llm():
    mock = MagicMock()
    mock.generate = AsyncMock(
        return_value=LLMResponse("Prompt response", 10, "mock-model", True)
    )
    mock.generate_intervention = AsyncMock(
        return_value=LLMResponse("Intervention response", 10, "mock-model", True)
    )
    mock.generate_summary = AsyncMock(
        return_value=LLMResponse("Summary response", 10, "mock-model", True)
    )
    return mock


@pytest.fixture
def service(mock_llm):
    return ChatInterventionService(llm_service=mock_llm)


class TestInterventionTypesAndResult:
    def test_enum_values(self):
        assert InterventionType.REDIRECT.value == "redirect"
        assert InterventionType.PROMPT.value == "prompt"
        assert InterventionType.SUMMARIZE.value == "summarize"
        assert InterventionType.CLARIFY.value == "clarify"
        assert InterventionType.RESOURCE.value == "resource"
        assert InterventionType.ENCOURAGE.value == "encourage"

    def test_result_fields(self):
        result = InterventionResult(
            message="msg",
            intervention_type=InterventionType.REDIRECT,
            confidence=0.7,
            should_intervene=True,
            reason="why",
            success=True,
            error=None,
        )

        assert result.message == "msg"
        assert result.success is True


class TestChatInterventionService:
    def test_init(self, mock_llm):
        svc = ChatInterventionService(llm_service=mock_llm)
        assert svc.llm_service is mock_llm

    def test_init_default_llm(self):
        with patch("app.services.intervention.get_llm_service", return_value=MagicMock()) as mock_get:
            svc = ChatInterventionService()
        mock_get.assert_called_once()
        assert svc.llm_service is not None

    @pytest.mark.asyncio
    async def test_analyze_no_messages(self, service):
        result = await service.analyze_and_intervene([], "topic", "room")
        assert result.should_intervene is False
        assert result.reason == "No messages to analyze"

    @pytest.mark.asyncio
    async def test_analyze_off_topic(self, service, mock_llm):
        messages = [
            {"sender": "u1", "content": "film kopi musik stadion"},
            {"sender": "u2", "content": "konser tiket hujan kamera"},
            {"sender": "u3", "content": "makanan liburan pantai laptop"},
            {"sender": "u4", "content": "game sepatu meja motor"},
            {"sender": "u5", "content": "basket kursi gitar jalan"},
        ]

        result = await service.analyze_and_intervene(messages, "Machine Learning", "room")

        assert result.success is True
        assert result.should_intervene is True
        assert result.intervention_type == InterventionType.REDIRECT
        mock_llm.generate_intervention.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_analyze_generation_exception(self, service, mock_llm):
        mock_llm.generate_intervention.side_effect = RuntimeError("boom")
        messages = [
            {"sender": "u1", "content": "film kopi musik stadion"},
            {"sender": "u2", "content": "konser tiket hujan kamera"},
            {"sender": "u3", "content": "makanan liburan pantai laptop"},
            {"sender": "u4", "content": "game sepatu meja motor"},
            {"sender": "u5", "content": "basket kursi gitar jalan"},
        ]

        result = await service.analyze_and_intervene(messages, "Machine Learning", "room")
        assert result.success is False
        assert result.error == "Internal error"

    @pytest.mark.asyncio
    async def test_check_triggers_inactive(self, service):
        messages = [{"content": "hello", "timestamp": datetime.now() - timedelta(minutes=40)}]
        triggers = await service._check_triggers(messages, "topic", None)
        assert triggers["inactive"] is True
        assert triggers["should_intervene"] is True

    @pytest.mark.asyncio
    async def test_check_triggers_summary(self, service):
        now = datetime.now()
        messages = [{"content": f"msg {i}", "timestamp": now.isoformat()} for i in range(10)]
        triggers = await service._check_triggers(messages, "topic", now - timedelta(minutes=1))
        assert triggers["needs_summary"] is True

    @pytest.mark.asyncio
    async def test_check_triggers_off_topic(self, service):
        messages = [{"content": "film kopi musik stadion"} for _ in range(5)]
        triggers = await service._check_triggers(messages, "Machine Learning", None)
        assert triggers["off_topic"] is True

    def test_select_intervention_variants(self, service):
        assert service._select_intervention({"off_topic": True, "off_topic_score": 0.9})[0] == InterventionType.REDIRECT
        assert service._select_intervention({"inactive": True})[0] == InterventionType.ENCOURAGE
        assert service._select_intervention({"needs_summary": True})[0] == InterventionType.SUMMARIZE
        assert service._select_intervention({"low_engagement": True})[0] == InterventionType.PROMPT
        assert service._select_intervention({})[0] == InterventionType.ENCOURAGE

    @pytest.mark.asyncio
    async def test_generate_summary_short_messages(self, service):
        result = await service.generate_summary([{"content": "hi"}], "room")
        assert result.should_intervene is False
        assert "Belum cukup pesan" in result.message

    @pytest.mark.asyncio
    async def test_generate_summary_success(self, service, mock_llm):
        messages = [{"content": f"msg {i}"} for i in range(10)]
        result = await service.generate_summary(messages, "room")
        assert result.message == "Summary response"
        mock_llm.generate_summary.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_summary_exception(self, service, mock_llm):
        mock_llm.generate_summary.side_effect = RuntimeError("summary failed")
        messages = [{"content": f"msg {i}"} for i in range(10)]
        result = await service.generate_summary(messages, "room")
        assert result.success is False
        assert result.error == "Internal error"

    @pytest.mark.asyncio
    async def test_generate_discussion_prompt_success(self, service, mock_llm):
        result = await service.generate_discussion_prompt("AI Ethics", context="class context", difficulty="hard")
        assert result.message == "Prompt response"
        called_prompt = mock_llm.generate.await_args.kwargs["prompt"]
        assert "AI Ethics" in called_prompt
        assert "class context" in called_prompt

    @pytest.mark.asyncio
    async def test_generate_discussion_prompt_unsuccessful_response(self, service, mock_llm):
        mock_llm.generate.return_value = LLMResponse("", 0, "mock-model", False, error="llm failed")
        result = await service.generate_discussion_prompt("AI Ethics")
        assert result.success is False
        assert result.error == "llm failed"

    @pytest.mark.asyncio
    async def test_generate_discussion_prompt_exception(self, service, mock_llm):
        mock_llm.generate.side_effect = RuntimeError("prompt failed")
        result = await service.generate_discussion_prompt("AI Ethics")
        assert result.success is False
        assert result.error == "Internal error"


class TestGetInterventionService:
    def test_singleton(self):
        intervention._intervention_service = None
        with patch("app.services.intervention.get_llm_service", return_value=MagicMock()):
            s1 = get_intervention_service()
            s2 = get_intervention_service()
        assert s1 is s2

    def test_uses_default_llm_factory(self):
        intervention._intervention_service = None
        mock_llm = MagicMock()
        with patch("app.services.intervention.get_llm_service", return_value=mock_llm):
            service = get_intervention_service()
        assert service.llm_service is mock_llm
