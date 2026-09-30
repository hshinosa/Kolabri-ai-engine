"""Regression tests for chat.py/goals.py fixes (B2 ensure_ready, B3 provider_context)."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router
from app.core.error_handlers import (
    ExceptionMiddleware,
    http_exception_handler,
    validation_exception_handler,
)

app = FastAPI()
app.include_router(router)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_middleware(ExceptionMiddleware)
client = TestClient(app, raise_server_exceptions=False)

PROVIDER_CONTEXT = {
    "version": "1.0",
    "provider": {"name": "openai", "displayName": "OpenAI GPT"},
    "execution": {"baseUrl": "https://provider.example/v1", "model": "gpt-4o-mini"},
    "auth": {"type": "api-key", "credential": "sk-provider-key"},
    "metadata": {
        "featureFamily": "personal_chat",
        "requestId": "req-1",
        "resolvedAt": "2026-06-16T00:00:00.000Z",
    },
}


def _completion_response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(total_tokens=7),
    )


# --- B3: validate_goal must forward body.provider_context to get_orchestrator ---


@patch("app.api.routes.goals.get_orchestrator")
def test_validate_goal_json_body_forwards_provider_context(mock_get_orchestrator):
    orchestrator = MagicMock()
    orchestrator.validate_goal = AsyncMock(
        return_value={"is_valid": True, "score": 0.9, "feedback": "bagus"}
    )
    mock_get_orchestrator.return_value = orchestrator

    response = client.post(
        "/goals/validate",
        json={
            "goal_text": "Belajar AI minggu ini",
            "user_id": "u1",
            "session_discussion_id": "c1",
            "week_context": {"week": 3},
            "provider_context": PROVIDER_CONTEXT,
        },
    )

    assert response.status_code == 200
    assert response.json()["is_valid"] is True
    mock_get_orchestrator.assert_called_once()
    passed_ctx = mock_get_orchestrator.call_args.kwargs["provider_context"]
    assert passed_ctx is not None
    assert passed_ctx == PROVIDER_CONTEXT
    orchestrator.validate_goal.assert_awaited_once()


@patch("app.api.routes.goals.get_orchestrator")
def test_validate_goal_without_provider_context_passes_none(mock_get_orchestrator):
    orchestrator = MagicMock()
    orchestrator.validate_goal = AsyncMock(
        return_value={"is_valid": False, "score": 0.3, "feedback": "kurang"}
    )
    mock_get_orchestrator.return_value = orchestrator

    response = client.post(
        "/goals/validate",
        json={"goal_text": "Belajar AI", "user_id": "u1", "session_discussion_id": "c1"},
    )

    assert response.status_code == 200
    assert mock_get_orchestrator.call_args.kwargs["provider_context"] is None


@patch("app.api.routes.goals.get_orchestrator")
def test_validate_goal_form_forwards_provider_context(mock_get_orchestrator):
    orchestrator = MagicMock()
    orchestrator.validate_goal = AsyncMock(
        return_value={"is_valid": True, "score": 0.9, "feedback": "bagus"}
    )
    mock_get_orchestrator.return_value = orchestrator

    response = client.post(
        "/goals/validate",
        data={
            "goal_text": "Belajar AI minggu ini",
            "user_id": "u1",
            "session_discussion_id": "c1",
            "provider_context": json.dumps(PROVIDER_CONTEXT),
        },
    )

    assert response.status_code == 200
    passed_ctx = mock_get_orchestrator.call_args.kwargs["provider_context"]
    assert passed_ctx == PROVIDER_CONTEXT


@patch("app.api.routes.goals.get_orchestrator")
def test_validate_goal_form_invalid_provider_context_falls_back_to_none(
    mock_get_orchestrator,
):
    orchestrator = MagicMock()
    orchestrator.validate_goal = AsyncMock(
        return_value={"is_valid": True, "score": 0.9, "feedback": "bagus"}
    )
    mock_get_orchestrator.return_value = orchestrator

    response = client.post(
        "/goals/validate",
        data={
            "goal_text": "Belajar AI minggu ini",
            "user_id": "u1",
            "session_discussion_id": "c1",
            "provider_context": "not-json-at-all",
        },
    )

    assert response.status_code == 200
    assert mock_get_orchestrator.call_args.kwargs["provider_context"] is None


# --- B2: personal_chat must await ensure_ready before touching llm.client ---


@patch("app.api.routes.chat.get_llm_service")
def test_personal_chat_stream_awaits_ensure_ready_before_using_client(mock_get_llm):
    """Mirrors the lazy unified-mode service: client/model only exist after
    ensure_ready(). The (now stream-only) personal chat path must await it
    before touching llm.client — pre-fix the non-stream handler used
    llm.client directly and AttributeError made every request fail."""
    service = SimpleNamespace(client=None, model=None)

    async def _stream(chunks):
        for content in chunks:
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
            )

    stream_create = AsyncMock(return_value=_stream(["Halo juga"]))

    async def _configure():
        service.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=stream_create))
        )
        service.model = "gpt-test"

    service.ensure_ready = AsyncMock(side_effect=_configure)
    mock_get_llm.return_value = service

    response = client.post(
        "/chat/personal/stream",
        json={"message": "halo-ensure-ready-probe", "history": []},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'data: {"content": "Halo juga"}' in response.text
    assert "data: [DONE]" in response.text
    service.ensure_ready.assert_awaited_once()
    stream_create.assert_awaited_once()
    assert stream_create.call_args.kwargs["model"] == "gpt-test"
