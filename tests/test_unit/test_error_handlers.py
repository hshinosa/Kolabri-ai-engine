"""Unit tests for app.core.error_handlers exception paths."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.error_handlers import (
    ExceptionMiddleware,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.services.llm import LLMDegradedError


def _request(path: str = "/x", *, request_id: str | None = "rid-1") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": b"",
        "server": ("test", 80),
        "client": ("test", 1234),
        "scheme": "http",
        "root_path": "",
    }
    req = Request(scope)
    if request_id is not None:
        req.state.request_id = request_id
    return req


@pytest.mark.asyncio
async def test_http_exception_4xx_and_5xx():
    req = _request()
    resp4 = await http_exception_handler(req, StarletteHTTPException(404, "missing"))
    assert resp4.status_code == 404
    assert resp4.body
    body4 = resp4.body.decode()
    assert "missing" in body4
    assert "outcome" not in body4

    resp5 = await http_exception_handler(req, StarletteHTTPException(500, "boom"))
    assert resp5.status_code == 500
    assert "terminal" in resp5.body.decode()


@pytest.mark.asyncio
async def test_http_exception_generates_request_id_when_missing():
    req = _request()
    del req.state.request_id
    resp = await http_exception_handler(req, StarletteHTTPException(400, "bad"))
    assert resp.status_code == 400
    assert "request_id" in resp.body.decode()


@pytest.mark.asyncio
async def test_validation_exception_handler():
    req = _request("/form")
    exc = RequestValidationError(
        errors=[{"loc": ["body", "x"], "msg": "required", "type": "missing"}]
    )
    resp = await validation_exception_handler(req, exc)
    assert resp.status_code == 422
    assert "VALIDATION_ERROR" in resp.body.decode()


@pytest.mark.asyncio
async def test_unhandled_exception_handler():
    req = _request()
    resp = await unhandled_exception_handler(req, RuntimeError("kaboom"))
    assert resp.status_code == 500
    body = resp.body.decode()
    assert "INTERNAL_SERVER_ERROR" in body
    assert "terminal" in body


@pytest.mark.asyncio
async def test_unhandled_exception_handler_redacts_credentials():
    req = _request()
    with patch("app.core.error_handlers.logger.error") as logger_error:
        await unhandled_exception_handler(
            req, RuntimeError("provider sk-secret-123 failed")
        )
    logger_error.assert_called_once()
    assert logger_error.call_args.kwargs["error"] == "provider [REDACTED]"


@pytest.mark.asyncio
async def test_unhandled_exception_request_id_fallback(monkeypatch):
    req = _request()

    def _boom(_req):
        raise RuntimeError("no rid")

    monkeypatch.setattr(
        "app.core.error_handlers._request_id_for",
        _boom,
    )
    with patch(
        "app.core.error_handlers.logger.error", side_effect=RuntimeError("log fail")
    ):
        resp = await unhandled_exception_handler(req, ValueError("inner"))
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_exception_middleware_reraises_http_and_validation():
    middleware = ExceptionMiddleware(app=MagicMock())

    async def _http(_req):
        raise StarletteHTTPException(404, "nope")

    with pytest.raises(StarletteHTTPException):
        await middleware.dispatch(_request(), _http)

    async def _validation(_req):
        raise RequestValidationError(errors=[])

    with pytest.raises(RequestValidationError):
        await middleware.dispatch(_request(), _validation)


def test_exception_middleware_passes_http_and_validation():
    app = FastAPI()
    app.add_middleware(ExceptionMiddleware)

    @app.get("/http")
    async def _http():
        raise StarletteHTTPException(418, "teapot")

    @app.get("/ok")
    async def _ok():
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/ok").status_code == 200
    assert client.get("/http").status_code == 418


def test_exception_middleware_maps_generic_to_500():
    app = FastAPI()
    app.add_middleware(ExceptionMiddleware)

    @app.get("/boom")
    async def _boom():
        raise RuntimeError("unexpected")

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "INTERNAL_SERVER_ERROR"


@pytest.mark.asyncio
async def test_exception_middleware_reraises_llm_degraded():
    middleware = ExceptionMiddleware(app=MagicMock())

    async def _call_next(_request):
        raise LLMDegradedError("open", 30)

    with pytest.raises(LLMDegradedError):
        await middleware.dispatch(_request("/degraded"), _call_next)
