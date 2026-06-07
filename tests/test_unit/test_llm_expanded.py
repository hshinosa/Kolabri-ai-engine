from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import llm as llm_module
from app.services.llm import ChatMessage, LLMResponse, OpenAILLMService, get_llm_service


@pytest.fixture
def llm_service():
    with patch("app.services.llm.httpx.AsyncClient"), \
         patch("app.services.llm.AsyncOpenAI"):
        with patch.object(llm_module.settings, "OPENAI_API_KEY", "test-key"), patch.object(
            llm_module.settings, "OPENAI_BASE_URL", "http://test"
        ), patch.object(llm_module.settings, "OPENAI_MODEL", "test-model"):
            yield OpenAILLMService()


def _response(content="Test response", tokens=10):
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    resp.usage = MagicMock(total_tokens=tokens)
    return resp


@pytest.mark.asyncio
async def test_generate_success(llm_service):
    llm_service.client.chat.completions.create = AsyncMock(return_value=_response("Test response"))
    response = await llm_service.generate("Hi")
    assert response.success is True
    assert response.content == "Test response"


@pytest.mark.asyncio
async def test_generate_failure(llm_service):
    llm_service.client.chat.completions.create = AsyncMock(side_effect=RuntimeError("Error"))
    response = await llm_service.generate("Hi failure")
    assert response.success is False
    assert response.error == "Internal error"


@pytest.mark.asyncio
async def test_generate_rag_response(llm_service):
    llm_service.generate = AsyncMock(return_value=LLMResponse("RAG response", 5, "test-model", True))
    response = await llm_service.generate_rag_response("Query", [])
    assert response.success is True
    assert response.content == "RAG response"


@pytest.mark.asyncio
async def test_generate_intervention(llm_service):
    llm_service.generate = AsyncMock(return_value=LLMResponse("Intervention", 5, "test-model", True))
    response = await llm_service.generate_intervention([])
    assert response.success is True
    assert response.content == "Intervention"


@pytest.mark.asyncio
async def test_generate_summary(llm_service):
    llm_service.generate = AsyncMock(return_value=LLMResponse("Summary", 5, "test-model", True))
    response = await llm_service.generate_summary([])
    assert response.success is True
    assert response.content == "Summary"


@pytest.mark.asyncio
async def test_reframe_to_socratic(llm_service):
    llm_service.generate = AsyncMock(return_value=LLMResponse("Socratic", 5, "test-model", True))
    response = await llm_service.reframe_to_socratic("Answer")
    assert response == "Socratic"


@pytest.mark.asyncio
async def test_get_goal_refinement_suggestion(llm_service):
    llm_service.generate = AsyncMock(return_value=LLMResponse("Refinement", 5, "test-model", True))
    response = await llm_service.get_goal_refinement_suggestion("Goal", [])
    assert response.success is True
    assert response.content == "Refinement"


def test_singleton():
    llm_module._llm_service = None
    with patch("app.services.llm.httpx.AsyncClient"), \
         patch("app.services.llm.AsyncOpenAI"):
        with patch.object(llm_module.settings, "OPENAI_API_KEY", "test-key"), patch.object(
            llm_module.settings, "OPENAI_BASE_URL", "http://test"
        ), patch.object(llm_module.settings, "OPENAI_MODEL", "test-model"):
            s1 = get_llm_service()
            s2 = get_llm_service()
    assert s1 is s2
