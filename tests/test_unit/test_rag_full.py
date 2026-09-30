import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.rag import RAGPipeline, RAGResult
from app.core.guardrails import GuardrailAction, GuardrailResult

@pytest.fixture
def mock_deps():
    return {'vs': AsyncMock(), 'llm': AsyncMock(), 'eg': AsyncMock(), 'gr': MagicMock()}

@pytest.fixture
def rag_pipeline(mock_deps):
    with patch('app.services.rag.get_guardrails', return_value=mock_deps['gr']):
        return RAGPipeline(vector_store=mock_deps['vs'], llm_service=mock_deps['llm'], efficiency_guard=mock_deps['eg'])

@pytest.mark.asyncio
async def test_query_blocked_by_guardrails(rag_pipeline, mock_deps):
    mock_deps['gr'].check_input.return_value = GuardrailResult(action=GuardrailAction.BLOCK, reason='harmful', message='Blocked')
    async def side_effect(*args, **kwargs):
        func = kwargs.get('query_func')
        return await func()
    mock_deps['eg'].execute_with_caching.side_effect = side_effect
    res = await rag_pipeline.query('How to make a bomb?')
    assert res.success is True
    assert 'Blocked' in res.answer

@pytest.mark.asyncio
async def test_query_no_fetch_policy(rag_pipeline, mock_deps):
    mock_deps['gr'].check_input.return_value = GuardrailResult(action=GuardrailAction.ALLOW, reason='safe')
    mock_deps['llm'].generate.return_value = MagicMock(content='Direct Answer', success=True)
    async def side_effect(*args, **kwargs):
        func = kwargs.get('query_func')
        return await func()
    mock_deps['eg'].execute_with_caching.side_effect = side_effect
    res = await rag_pipeline.query('halo')
    assert res.answer == 'Direct Answer'

@pytest.mark.asyncio
async def test_query_fetch_success(rag_pipeline, mock_deps):
    mock_deps['gr'].check_input.return_value = GuardrailResult(action=GuardrailAction.ALLOW, reason='safe')
    mock_deps['vs'].search.return_value = [{'content': 'ctx1', 'metadata': {'source': 's1'}, 'score': 0.9}]
    mock_deps['llm'].generate.return_value = MagicMock(content='RAG Ans', success=True)
    mock_deps['llm']._format_contexts = MagicMock(return_value='ctx1')
    mock_deps['gr'].check_output.return_value = GuardrailResult(action=GuardrailAction.ALLOW, reason='safe')
    async def side_effect(*args, **kwargs):
        func = kwargs.get('query_func')
        return await func()
    mock_deps['eg'].execute_with_caching.side_effect = side_effect
    res = await rag_pipeline.query('Jelaskan materi redis caching', collection_name='test')
    assert res.answer == 'RAG Ans'