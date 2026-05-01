from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.guardrails import GuardrailAction
from app.services.rag import RAGPipeline


@pytest.mark.asyncio
async def test_query_direct_execution():
    with patch("app.services.rag.get_guardrails") as mock_gr:
        guardrails = MagicMock()
        guardrails.check_input.return_value = MagicMock(
            action=GuardrailAction.ALLOW,
            sanitized_input=None,
            reason=None,
            message=None,
        )
        mock_gr.return_value = guardrails

        llm = MagicMock()
        llm.generate = AsyncMock(return_value=MagicMock(content="Direct Answer", tokens_used=5, success=True, error=None))

        pipe = RAGPipeline(vector_store=MagicMock(), llm_service=llm, efficiency_guard=None)
        res = await pipe.query("halo")

        assert res.answer == "Direct Answer"
        assert res.success is True
