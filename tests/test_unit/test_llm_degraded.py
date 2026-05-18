from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import APIConnectionError

from app.middleware.request_id import REQUEST_ID_HEADER, RequestIDMiddleware
from app.services.circuit_breaker import (
    CircuitState,
    get_llm_circuit_breaker,
)
from app.services.llm import LLMDegradedError, OpenAILLMService


@pytest.fixture(autouse=True)
def reset_breaker():
    breaker = get_llm_circuit_breaker()
    breaker.reset()
    yield
    breaker.reset()


@pytest.fixture
def llm_service():
    settings_patch = patch("app.services.llm.settings")
    httpx_patch = patch("app.services.llm.httpx.AsyncClient")
    openai_patch = patch("app.services.llm.AsyncOpenAI")

    mock_settings = settings_patch.start()
    httpx_patch.start()
    mock_openai = openai_patch.start()

    mock_settings.OPENAI_API_KEY = "test_key"
    mock_settings.OPENAI_BASE_URL = "https://api.test.com"
    mock_settings.OPENAI_MODEL = "test-model"
    mock_settings.OPENAI_TEMPERATURE = 0.7
    mock_settings.OPENAI_MAX_TOKENS = 1000
    mock_settings.LLM_TIMEOUT_CONNECT_SECONDS = 1.0
    mock_settings.LLM_TIMEOUT_READ_SECONDS = 5.0
    mock_settings.LLM_MAX_RETRIES = 3
    mock_settings.LLM_RETRY_DELAY_BASE = 0.01
    mock_settings.LLM_RETRY_DELAY_MULTIPLIER = 0.01
    mock_settings.LLM_RETRY_DEFAULT_RETRY_AFTER_SECONDS = 7
    mock_settings.ENV = "testing"

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=APIConnectionError(request=MagicMock())
    )
    mock_openai.return_value = mock_client

    service = OpenAILLMService()
    yield service, mock_client

    settings_patch.stop()
    httpx_patch.stop()
    openai_patch.stop()


@pytest.mark.asyncio
async def test_breaker_open_raises_degraded(llm_service):
    service, _ = llm_service
    breaker = get_llm_circuit_breaker()
    breaker._state = CircuitState.OPEN
    breaker._last_failure_time = datetime.now()

    with pytest.raises(LLMDegradedError) as exc_info:
        await service.generate(prompt="hi")
    assert exc_info.value.reason == "llm_circuit_open"
    assert exc_info.value.retry_after >= 1


@pytest.mark.asyncio
async def test_retry_exhaustion_raises_degraded(llm_service):
    service, _ = llm_service
    with pytest.raises(LLMDegradedError) as exc_info:
        await service.generate(prompt="hi")
    assert exc_info.value.reason == "llm_retry_exhausted"
    assert exc_info.value.retry_after == 7


def test_degraded_handler_returns_503_with_outcome():
    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        yield

    from main import llm_degraded_exception_handler

    app = FastAPI(lifespan=_lifespan)
    app.add_middleware(RequestIDMiddleware)
    app.add_exception_handler(LLMDegradedError, llm_degraded_exception_handler)

    @app.get("/boom")
    async def _boom():
        raise LLMDegradedError(reason="llm_circuit_open", retry_after=12)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")

    assert resp.status_code == 503
    body = resp.json()
    assert body["outcome"] == "degraded"
    assert body["reason"] == "llm_circuit_open"
    assert body["retry_after"] == 12
    assert "request_id" in body
    assert resp.headers.get("Retry-After") == "12"
    assert REQUEST_ID_HEADER in resp.headers
