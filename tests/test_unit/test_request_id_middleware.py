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


def test_empty_string_request_id_is_replaced(client: TestClient):
    """Empty string should be treated as invalid and replaced with new UUID."""
    resp = client.get("/echo", headers={REQUEST_ID_HEADER: ""})
    assert resp.status_code == 200
    rid = resp.headers[REQUEST_ID_HEADER]
    assert rid != ""
    uuid.UUID(rid)  # Should be valid UUID


def test_whitespace_only_request_id_is_replaced(client: TestClient):
    """Whitespace-only values should be replaced."""
    resp = client.get("/echo", headers={REQUEST_ID_HEADER: "   "})
    assert resp.status_code == 200
    rid = resp.headers[REQUEST_ID_HEADER]
    uuid.UUID(rid)


def test_malformed_uuid_variations(client: TestClient):
    """Test various malformed UUID formats."""
    malformed_values = [
        "not-a-uuid",
        "12345",
        "11111111-2222-3333-4444",  # Too short
        "11111111-2222-3333-4444-555555555555-extra",  # Too long
        "gggggggg-hhhh-iiii-jjjj-kkkkkkkkkkkk",  # Invalid hex chars
        "11111111222233334444555555555555",  # No dashes
    ]

    for bad_value in malformed_values:
        resp = client.get("/echo", headers={REQUEST_ID_HEADER: bad_value})
        assert resp.status_code == 200
        rid = resp.headers[REQUEST_ID_HEADER]
        assert rid != bad_value, f"Bad value '{bad_value}' should have been replaced"
        uuid.UUID(rid)  # Should be valid UUID


def test_request_id_propagated_to_request_state(client: TestClient):
    """Verify request ID is accessible via request.state."""
    inbound = "12345678-1234-5678-1234-567812345678"
    resp = client.get("/echo", headers={REQUEST_ID_HEADER: inbound})
    assert resp.status_code == 200
    data = resp.json()
    assert data["state_request_id"] == inbound
    assert data["ctx_request_id"] == inbound


def test_structlog_context_bound_during_request(client: TestClient):
    """Verify structlog context is properly bound during request processing."""
    inbound = "87654321-4321-8765-4321-876543218765"
    resp = client.get("/echo", headers={REQUEST_ID_HEADER: inbound})
    assert resp.status_code == 200
    data = resp.json()
    # During request, context should have the request_id
    assert data["ctx_request_id"] == inbound


def test_multiple_requests_isolated(client: TestClient):
    """Each request should have its own isolated request ID context."""
    id1 = "11111111-1111-1111-1111-111111111111"
    id2 = "22222222-2222-2222-2222-222222222222"

    resp1 = client.get("/echo", headers={REQUEST_ID_HEADER: id1})
    resp2 = client.get("/echo", headers={REQUEST_ID_HEADER: id2})

    assert resp1.headers[REQUEST_ID_HEADER] == id1
    assert resp2.headers[REQUEST_ID_HEADER] == id2
    assert resp1.json()["state_request_id"] == id1
    assert resp2.json()["state_request_id"] == id2


def test_generated_uuids_are_unique(client: TestClient):
    """When no request ID provided, each request should get unique UUID."""
    resp1 = client.get("/echo")
    resp2 = client.get("/echo")

    id1 = resp1.headers[REQUEST_ID_HEADER]
    id2 = resp2.headers[REQUEST_ID_HEADER]

    assert id1 != id2
    uuid.UUID(id1)
    uuid.UUID(id2)


def test_request_id_header_case_insensitive(client: TestClient):
    """HTTP headers are case-insensitive, middleware should handle this."""
    inbound = "55555555-5555-5555-5555-555555555555"
    # Test with different case variations
    for header_name in ["X-Request-ID", "x-request-id", "X-REQUEST-ID"]:
        resp = client.get("/echo", headers={header_name: inbound})
        assert resp.status_code == 200
        # Response header should always be the canonical form
        assert resp.headers[REQUEST_ID_HEADER] == inbound
