from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from app.middleware.request_id import (
    REQUEST_ID_CONTEXT_KEY,
    REQUEST_ID_HEADER,
    RequestIDMiddleware,
)


def _make_app() -> FastAPI:
    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        yield

    app = FastAPI(lifespan=_lifespan)
    app.add_middleware(RequestIDMiddleware)

    @app.get("/echo")
    async def _echo(request: Request):
        return {
            "state_request_id": request.state.request_id,
            "ctx_request_id": structlog.contextvars.get_contextvars().get(
                REQUEST_ID_CONTEXT_KEY
            ),
        }

    @app.get("/boom")
    async def _boom():
        raise HTTPException(status_code=418, detail="kettle")

    return app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(_make_app(), raise_server_exceptions=False)


def test_response_carries_x_request_id_when_inbound_missing(client: TestClient):
    resp = client.get("/echo")
    assert resp.status_code == 200
    assert REQUEST_ID_HEADER in resp.headers
    rid = resp.headers[REQUEST_ID_HEADER]
    uuid.UUID(rid)
    assert resp.json()["state_request_id"] == rid
    assert resp.json()["ctx_request_id"] == rid


def test_valid_inbound_uuid_is_reused(client: TestClient):
    inbound = "11111111-2222-3333-4444-555555555555"
    resp = client.get("/echo", headers={REQUEST_ID_HEADER: inbound})
    assert resp.status_code == 200
    assert resp.headers[REQUEST_ID_HEADER] == inbound
    assert resp.json()["state_request_id"] == inbound


def test_invalid_inbound_value_is_replaced(client: TestClient):
    bad = "<script>alert(1)</script>"
    resp = client.get("/echo", headers={REQUEST_ID_HEADER: bad})
    assert resp.status_code == 200
    rid = resp.headers[REQUEST_ID_HEADER]
    assert rid != bad
    uuid.UUID(rid)


def test_contextvar_unbinds_after_request(client: TestClient):
    structlog.contextvars.unbind_contextvars(REQUEST_ID_CONTEXT_KEY)
    client.get("/echo")
    assert (
        REQUEST_ID_CONTEXT_KEY
        not in structlog.contextvars.get_contextvars()
    )


def test_http_exception_response_carries_request_id_via_handler(client: TestClient):
    inbound = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    resp = client.get("/boom", headers={REQUEST_ID_HEADER: inbound})
    assert resp.status_code == 418
    assert resp.headers[REQUEST_ID_HEADER] == inbound
