from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api.guarded_response import (
    DEFAULT_GUARDED_MESSAGE,
    RULE_MESSAGE_MAP,
    guarded_response,
)
from app.middleware.request_id import REQUEST_ID_HEADER, RequestIDMiddleware


def _make_app() -> FastAPI:
    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        yield

    app = FastAPI(lifespan=_lifespan)
    app.add_middleware(RequestIDMiddleware)

    @app.get("/chat-block")
    async def _chat_block(request: Request):
        return guarded_response(
            rule_id="academic_dishonesty",
            surface="chat",
            request_id=request.state.request_id,
        )

    @app.get("/non-chat-block")
    async def _non_chat_block(request: Request):
        return guarded_response(
            rule_id="prompt_injection",
            surface="non_chat",
            request_id=request.state.request_id,
        )

    @app.get("/unknown-rule")
    async def _unknown(request: Request):
        return guarded_response(
            rule_id="some_unknown_rule",
            surface="chat",
            request_id=request.state.request_id,
        )

    return app


def test_chat_guarded_returns_200_with_outcome():
    client = TestClient(_make_app(), raise_server_exceptions=False)
    resp = client.get("/chat-block")
    assert resp.status_code == 200
    body = resp.json()
    assert body["outcome"] == "guarded"
    assert body["reason"] == "academic_dishonesty"
    assert body["message"] == RULE_MESSAGE_MAP["academic_dishonesty"]
    assert body["detail"] == "GUARDED"
    assert "triggered_rules" not in body
    assert "request_id" in body


def test_non_chat_guarded_returns_403_with_outcome():
    client = TestClient(_make_app(), raise_server_exceptions=False)
    resp = client.get("/non-chat-block")
    assert resp.status_code == 403
    body = resp.json()
    assert body["outcome"] == "guarded"
    assert body["reason"] == "prompt_injection"
    assert body["message"] == RULE_MESSAGE_MAP["prompt_injection"]
    assert "triggered_rules" not in body


def test_unknown_rule_uses_default_message():
    client = TestClient(_make_app(), raise_server_exceptions=False)
    resp = client.get("/unknown-rule")
    assert resp.json()["message"] == DEFAULT_GUARDED_MESSAGE


def test_guarded_response_carries_request_id_header():
    client = TestClient(_make_app(), raise_server_exceptions=False)
    inbound = "11111111-1111-1111-1111-111111111111"
    resp = client.get("/chat-block", headers={REQUEST_ID_HEADER: inbound})
    assert resp.headers[REQUEST_ID_HEADER] == inbound
    assert resp.json()["request_id"] == inbound


def test_global_handler_carries_terminal_outcome():
    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        yield

    from main import global_exception_handler

    app = FastAPI(lifespan=_lifespan)
    app.add_middleware(RequestIDMiddleware)
    app.add_exception_handler(Exception, global_exception_handler)

    @app.get("/boom")
    async def _boom():
        raise RuntimeError("kaboom")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body["outcome"] == "terminal"
    assert body["detail"] == "INTERNAL_SERVER_ERROR"
    assert "request_id" in body
