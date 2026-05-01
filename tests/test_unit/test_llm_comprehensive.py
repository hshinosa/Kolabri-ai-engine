"""Comprehensive tests for the current LLM service implementation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIError

from app.services import llm as llm_module
from app.services.llm import ChatMessage, LLMResponse, OpenAILLMService, get_llm_service


def _mock_completion(content="Test response", tokens=50, usage=True):
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    resp.usage = MagicMock(total_tokens=tokens) if usage else None
    return resp


@pytest.fixture
def mock_openai_client():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_completion())
    return client


@pytest.fixture
def llm_service(mock_openai_client):
    with patch("app.services.llm.AsyncOpenAI", return_value=mock_openai_client):
        with patch.object(llm_module.settings, "OPENAI_API_KEY", "test_key"), patch.object(
            llm_module.settings, "OPENAI_BASE_URL", "http://test.com"
        ), patch.object(llm_module.settings, "OPENAI_MODEL", "test-model"), patch.object(
            llm_module.settings, "OPENAI_TEMPERATURE", 0.7
        ), patch.object(
            llm_module.settings, "OPENAI_MAX_TOKENS", 2048
        ), patch.object(
            llm_module.settings, "SCAFFOLDING_FULL_THRESHOLD", 0.3
        ), patch.object(
            llm_module.settings, "SCAFFOLDING_MINIMAL_THRESHOLD", 0.7
        ), patch.object(
            llm_module.settings, "ENV", "testing"
        ):
            yield OpenAILLMService()


class TestLLMResponse:
    def test_llm_response_success(self):
        response = LLMResponse("Test content", 50, "test-model", True)
        assert response.content == "Test content"
        assert response.error is None

    def test_llm_response_with_error(self):
        response = LLMResponse("", 0, "test-model", False, error="Test error")
        assert response.success is False
        assert response.error == "Test error"


class TestChatMessage:
    def test_chat_message_roles(self):
        assert ChatMessage(role="user", content="Hello").role == "user"
        assert ChatMessage(role="assistant", content="Hi").role == "assistant"
        assert ChatMessage(role="system", content="System").role == "system"


class TestOpenAILLMService:
    def test_init(self, mock_openai_client):
        with patch("app.services.llm.AsyncOpenAI", return_value=mock_openai_client):
            with patch.object(llm_module.settings, "OPENAI_API_KEY", "test_key"), patch.object(
                llm_module.settings, "OPENAI_BASE_URL", "http://test.com"
            ), patch.object(llm_module.settings, "OPENAI_MODEL", "test-model"), patch.object(
                llm_module.settings, "OPENAI_TEMPERATURE", 0.7
            ), patch.object(
                llm_module.settings, "OPENAI_MAX_TOKENS", 2048
            ):
                service = OpenAILLMService()
        assert service.client is not None
        assert service.model == "test-model"
        assert service.temperature == 0.7
        assert service.max_tokens == 2048

    def test_init_no_api_key(self):
        with patch.object(llm_module.settings, "OPENAI_API_KEY", ""):
            with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
                OpenAILLMService()

    def test_system_prompts(self):
        assert {"default", "rag", "intervention", "summary"}.issubset(OpenAILLMService.SYSTEM_PROMPTS)

    @pytest.mark.asyncio
    async def test_generate_success(self, llm_service):
        response = await llm_service.generate("Test prompt")
        assert response.success is True
        assert response.content == "Test response"
        assert response.tokens_used == 50

    @pytest.mark.asyncio
    async def test_generate_with_options(self, llm_service):
        response = await llm_service.generate(
            "Test prompt", system_prompt="Custom system prompt", context="This is context", temperature=0.9, max_tokens=123
        )
        assert response.success is True

    @pytest.mark.asyncio
    async def test_generate_api_error_returns_failure_response(self, llm_service):
        llm_service.client.chat.completions.create = AsyncMock(side_effect=RuntimeError("Test error"))
        response = await llm_service.generate("Test prompt")
        assert response.success is False
        assert "Test error" in response.error

    @pytest.mark.asyncio
    async def test_generate_empty_content(self, llm_service):
        llm_service.client.chat.completions.create = AsyncMock(return_value=_mock_completion(content=None, tokens=0))
        response = await llm_service.generate("Test prompt")
        assert response.success is True
        assert response.content == ""

    @pytest.mark.asyncio
    async def test_generate_no_usage(self, llm_service):
        llm_service.client.chat.completions.create = AsyncMock(return_value=_mock_completion("Response", usage=False))
        response = await llm_service.generate("Test prompt")
        assert response.tokens_used == 0

    @pytest.mark.asyncio
    async def test_generate_rag_response(self, llm_service):
        llm_service.generate = AsyncMock(return_value=LLMResponse("RAG response", 42, "test-model", True))
        response = await llm_service.generate_rag_response("Test query", [{"content": "Context 1"}])
        assert response.content == "RAG response"

    @pytest.mark.asyncio
    async def test_generate_rag_response_with_history(self, llm_service):
        llm_service.generate = AsyncMock(return_value=LLMResponse("RAG response", 42, "test-model", True))
        history = [ChatMessage(role="user", content="Hello"), ChatMessage(role="assistant", content="Hi")]
        response = await llm_service.generate_rag_response("Test", [{"content": "Context"}], chat_history=history)
        assert response.success is True

    def test_get_scaffolding_instruction(self, llm_service):
        assert "langkah-demi-langkah" in llm_service._get_scaffolding_instruction(0.1)
        assert "petunjuk umum" in llm_service._get_scaffolding_instruction(0.5)
        assert "Socratic Questioning" in llm_service._get_scaffolding_instruction(0.8)

    @pytest.mark.asyncio
    async def test_generate_intervention(self, llm_service):
        llm_service.generate = AsyncMock(return_value=LLMResponse("Intervention", 10, "test-model", True))
        messages = [{"sender": "User1", "content": "Message 1"}, {"sender": "User2", "content": "Message 2"}]
        response = await llm_service.generate_intervention(chat_messages=messages, intervention_type="redirect", topic="AI")
        assert response.success is True

    @pytest.mark.asyncio
    async def test_generate_summary(self, llm_service):
        llm_service.generate = AsyncMock(return_value=LLMResponse("Summary", 10, "test-model", True))
        response = await llm_service.generate_summary([{"sender": "User1", "content": "Hello"}])
        assert response.success is True

    @pytest.mark.asyncio
    async def test_reframe_to_socratic_success_and_failure(self, llm_service):
        llm_service.generate = AsyncMock(return_value=LLMResponse("Question back", 10, "test-model", True))
        assert await llm_service.reframe_to_socratic("Direct answer") == "Question back"

        llm_service.generate = AsyncMock(return_value=LLMResponse("", 0, "test-model", False, error="x"))
        assert await llm_service.reframe_to_socratic("Direct answer") == "Direct answer"

    @pytest.mark.asyncio
    async def test_get_goal_refinement_suggestion(self, llm_service):
        llm_service.generate = AsyncMock(return_value=LLMResponse("Refine it", 10, "test-model", True))
        response = await llm_service.get_goal_refinement_suggestion("Learn Python", ["Specific"])
        assert response.success is True

    def test_format_contexts(self, llm_service):
        result = llm_service._format_contexts([
            {"content": "First context", "metadata": {"source": "a.pdf", "page": 1}},
            {"content": "Second context", "metadata": {"source": "b.pdf", "page": 2}},
        ])
        assert "[1] Sumber: a.pdf" in result
        assert "First context" in result
        assert "Second context" in result

    def test_format_contexts_empty_and_missing(self, llm_service):
        assert llm_service._format_contexts([]) == ""
        result = llm_service._format_contexts([{"other": "data"}])
        assert "Unknown" in result

    def test_format_chat_history(self, llm_service):
        history = [ChatMessage(role="user", content="Hello"), ChatMessage(role="assistant", content="Hi there")]
        result = llm_service._format_chat_history(history)
        assert "Mahasiswa: Hello" in result
        assert "Asisten: Hi there" in result

    def test_format_chat_history_truncated_and_empty(self, llm_service):
        history = [ChatMessage(role="user", content=f"Msg {i}") for i in range(10)]
        result = llm_service._format_chat_history(history)
        assert "Msg 9" in result
        assert "Msg 0" not in result
        assert llm_service._format_chat_history([]) == ""


class TestGetLLMService:
    def test_get_llm_service_singleton(self):
        llm_module._llm_service = None
        with patch("app.services.llm.AsyncOpenAI"):
            with patch.object(llm_module.settings, "OPENAI_API_KEY", "test_key"), patch.object(
                llm_module.settings, "OPENAI_BASE_URL", "http://test.com"
            ), patch.object(llm_module.settings, "OPENAI_MODEL", "test-model"):
                service1 = get_llm_service()
                service2 = get_llm_service()
        assert service1 is service2
        assert isinstance(service1, OpenAILLMService)
