import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.llm import OpenAILLMService, LLMResponse, ChatMessage

@pytest.fixture
def llm_service():
    with patch('app.services.llm.httpx.AsyncClient') as mock_httpx, \
         patch('app.services.llm.AsyncOpenAI') as mock_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock()
        mock_openai.return_value = mock_client
        
        service = OpenAILLMService()
        yield service, mock_client

@pytest.mark.asyncio
async def test_generate_success(llm_service):
    service, mock_client = llm_service
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = 'Test response'
    mock_resp.usage.total_tokens = 10
    mock_client.chat.completions.create.return_value = mock_resp
    
    response = await service.generate('Hi')
    assert response.success is True
    assert response.content == 'Test response'

@pytest.mark.asyncio
async def test_generate_retry_logic(llm_service):
    service, mock_client = llm_service
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = 'Success after retry'
    mock_resp.usage.total_tokens = 10
    
    # Simulate one failure then success
    from openai import APIConnectionError
    mock_client.chat.completions.create.side_effect = [
        APIConnectionError(message='Error', request=MagicMock()),
        mock_resp
    ]
    
    # Patch sleep to speed up test
    with patch('asyncio.sleep', AsyncMock()):
        response = await service.generate('Hi')
        assert response.success is True
        assert response.content == 'Success after retry'
        assert mock_client.chat.completions.create.call_count == 2

@pytest.mark.asyncio
async def test_generate_rag_response(llm_service):
    service, _ = llm_service
    with patch.object(service, 'generate', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = LLMResponse(content='RAG response', tokens_used=10, model='m', success=True)
        response = await service.generate_rag_response('Query', [{'content': 'c1'}])
        assert response.content == 'RAG response'

@pytest.mark.asyncio
async def test_generate_intervention(llm_service):
    service, _ = llm_service
    with patch.object(service, 'generate', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = LLMResponse(content='Intervention', tokens_used=10, model='m', success=True)
        response = await service.generate_intervention([{'content': 'msg'}])
        assert response.content == 'Intervention'

@pytest.mark.asyncio
async def test_generate_summary(llm_service):
    service, _ = llm_service
    with patch.object(service, 'generate', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = LLMResponse(content='Summary', tokens_used=10, model='m', success=True)
        response = await service.generate_summary([{'content': 'msg'}])
        assert response.content == 'Summary'

@pytest.mark.asyncio
async def test_reframe_to_socratic(llm_service):
    service, _ = llm_service
    with patch.object(service, 'generate', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = LLMResponse(content='Socratic', tokens_used=10, model='m', success=True)
        response = await service.reframe_to_socratic('Direct')
        assert response == 'Socratic'

@pytest.mark.asyncio
async def test_get_goal_refinement_suggestion(llm_service):
    service, _ = llm_service
    with patch.object(service, 'generate', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = LLMResponse(content='Refinement', tokens_used=10, model='m', success=True)
        response = await service.get_goal_refinement_suggestion('Goal', ['Criteria'])
        assert response.success is True
        assert response.content == 'Refinement'