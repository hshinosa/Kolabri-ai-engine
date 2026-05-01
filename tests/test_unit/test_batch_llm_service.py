"""Tests for app/services/batch_llm.py"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.batch_llm import BatchLLMService, BatchResult


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.generate = AsyncMock()
    return llm


@pytest.fixture
def batch_service(mock_llm):
    return BatchLLMService(llm_service=mock_llm)


class TestBatchResult:
    def test_batch_result_success(self):
        r = BatchResult(success=True, content="answer", tokens_used=50)
        assert r.success is True
        assert r.content == "answer"
        assert r.tokens_used == 50
        assert r.error is None
    
    def test_batch_result_failure(self):
        r = BatchResult(success=False, content="", tokens_used=0, error="timeout")
        assert r.success is False
        assert r.error == "timeout"


class TestBatchLLMGenerateBatch:
    @pytest.mark.asyncio
    async def test_empty_prompts(self, batch_service):
        result = await batch_service.generate_batch([])
        assert result == []
    
    @pytest.mark.asyncio
    async def test_single_prompt_success(self, batch_service, mock_llm):
        mock_llm.generate.return_value = MagicMock(
            success=True,
            content="[1] Answer one",
            tokens_used=100
        )
        
        result = await batch_service.generate_batch(["What is AI?"])
        assert len(result) == 1
        assert result[0].success is True
        assert "Answer one" in result[0].content
    
    @pytest.mark.asyncio
    async def test_multiple_prompts_success(self, batch_service, mock_llm):
        mock_llm.generate.return_value = MagicMock(
            success=True,
            content="[1] First answer [2] Second answer [3] Third answer",
            tokens_used=300
        )
        
        result = await batch_service.generate_batch(["q1", "q2", "q3"])
        assert len(result) == 3
        assert all(r.success for r in result)
        assert "First answer" in result[0].content
        assert "Second answer" in result[1].content
        assert "Third answer" in result[2].content
    
    @pytest.mark.asyncio
    async def test_llm_failure_returns_all_failed(self, batch_service, mock_llm):
        mock_llm.generate.return_value = MagicMock(
            success=False,
            content="",
            tokens_used=0,
            error="Rate limited"
        )
        
        result = await batch_service.generate_batch(["q1", "q2"])
        assert len(result) == 2
        assert all(not r.success for r in result)
        assert all(r.error == "Rate limited" for r in result)
    
    @pytest.mark.asyncio
    async def test_exception_returns_all_failed(self, batch_service, mock_llm):
        mock_llm.generate.side_effect = Exception("Network error")
        
        result = await batch_service.generate_batch(["q1", "q2"])
        assert len(result) == 2
        assert all(not r.success for r in result)
        assert all("Network error" in r.error for r in result)
    
    @pytest.mark.asyncio
    async def test_chunking_over_max_batch_size(self, batch_service, mock_llm):
        batch_service.max_batch_size = 3
        
        mock_llm.generate.return_value = MagicMock(
            success=True,
            content="[1] A1 [2] A2 [3] A3",
            tokens_used=150
        )
        
        prompts = [f"q{i}" for i in range(7)]
        result = await batch_service.generate_batch(prompts)
        
        assert len(result) == 7
        # Should have been called 3 times (3+3+1)
        assert mock_llm.generate.call_count == 3
    
    @pytest.mark.asyncio
    async def test_tokens_distributed_evenly(self, batch_service, mock_llm):
        mock_llm.generate.return_value = MagicMock(
            success=True,
            content="[1] A [2] B",
            tokens_used=200
        )
        
        result = await batch_service.generate_batch(["q1", "q2"])
        assert result[0].tokens_used == 100
        assert result[1].tokens_used == 100


class TestBatchLLMCombinePrompts:
    def test_combine_single_prompt(self, batch_service):
        combined = batch_service._combine_prompts(["Hello"])
        assert "[1] Hello" in combined
        assert "Jawab semua pertanyaan" in combined
    
    def test_combine_multiple_prompts(self, batch_service):
        combined = batch_service._combine_prompts(["Q1", "Q2", "Q3"])
        assert "[1] Q1" in combined
        assert "[2] Q2" in combined
        assert "[3] Q3" in combined


class TestBatchLLMSplitResponses:
    def test_split_clean_format(self, batch_service):
        combined = "[1] First answer [2] Second answer [3] Third answer"
        result = batch_service._split_responses(combined, 3)
        
        assert len(result) == 3
        assert "First answer" in result[0]
        assert "Second answer" in result[1]
        assert "Third answer" in result[2]
    
    def test_split_missing_marker(self, batch_service):
        combined = "[1] Only first answer"
        result = batch_service._split_responses(combined, 2)
        
        assert len(result) == 2
        assert "Only first answer" in result[0]
        assert "tidak ditemukan" in result[1]
    
    def test_split_fills_missing(self, batch_service):
        combined = ""
        result = batch_service._split_responses(combined, 3)
        assert len(result) == 3


class TestBatchLLMModule:
    def test_get_batch_llm_service_singleton(self):
        import app.services.batch_llm as module
        module._batch_service = None
        
        with patch("app.services.batch_llm.get_llm_service") as mock_get:
            mock_get.return_value = MagicMock()
            svc = module.get_batch_llm_service()
            assert svc is not None
            
            svc2 = module.get_batch_llm_service()
            assert svc is svc2
        
        module._batch_service = None
