import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.rag import RAGPipeline, RAGResult
from app.core.guardrails import GuardrailAction

@pytest.fixture
def mock_deps():
    return {
        'vs': AsyncMock(),
        'llm': AsyncMock(),
        'eg': AsyncMock()
    }

@pytest.fixture
def rag_pipeline(mock_deps):
    with patch('app.services.rag.get_guardrails'):
        pipe = RAGPipeline(
            vector_store=mock_deps['vs'],
            llm_service=mock_deps['llm'],
            efficiency_guard=mock_deps['eg']
        )
        return pipe

@pytest.mark.asyncio
async def test_query_blocked_by_guardrails(rag_pipeline, mock_deps):
    # Setup mock result to be returned by execute_with_caching
    mock_result = RAGResult(answer='Blocked', sources=[], query='q', tokens_used=0, success=True)
    mock_deps['eg'].execute_with_caching.return_value = mock_result
    
    res = await rag_pipeline.query('How to make a bomb?')
    assert res.success is True
    assert res.answer == 'Blocked'


def test_rag_result_additive_fields():
    result = RAGResult(answer='Bot response', sources=[{'s':1}], query='q', tokens_used=50, success=True)
    assert result.scaffolding_triggered is False
    assert result.grounding_ratio == 1.0
    assert result.srl_phase is None
    assert result.srl_sub_phase is None

@pytest.mark.asyncio
async def test_query_fetch_success(rag_pipeline, mock_deps):
    mock_result = RAGResult(answer='RAG Answer', sources=[{'s':1}], query='q', tokens_used=50, success=True)
    mock_deps['eg'].execute_with_caching.return_value = mock_result
    
    res = await rag_pipeline.query('Jelaskan materi X')
    assert res.success is True
    assert res.answer == 'RAG Answer'
