from __future__ import annotations

import sys
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.api.routes import router as api_router  # noqa: E402
from app.middleware.request_id import REQUEST_ID_HEADER, RequestIDMiddleware  # noqa: E402
from app.services.logic_listener import get_logic_listener  # noqa: E402
from app.services.reranker import get_reranker  # noqa: E402


@asynccontextmanager
async def _mock_lifespan(_app: FastAPI):
    yield


def _build_app() -> FastAPI:
    app = FastAPI(title="Kolabri AI-Engine (Verify)", lifespan=_mock_lifespan)
    app.add_middleware(RequestIDMiddleware)
    app.include_router(api_router, prefix="/api")
    return app


def _assert(cond: bool, msg: str) -> None:
    status = "OK " if cond else "FAIL"
    print(f"  [{status}] {msg}")
    if not cond:
        raise SystemExit(1)


def main() -> int:
    app = _build_app()
    client = TestClient(app, raise_server_exceptions=True)

    print("== ai-engine-track-activity 3.2 / 3.3 ==")

    listener = get_logic_listener()
    group_id = "verify_group_001"
    before = listener._last_message_timestamp.get(group_id)

    resp = client.post("/api/track-activity", json={"group_id": group_id})
    _assert(resp.status_code == 200, f"status_code == 200 (got {resp.status_code})")
    _assert(resp.json() == {"success": True}, f"body == {{success: true}} (got {resp.json()})")

    after = listener._last_message_timestamp.get(group_id)
    _assert(
        after is not None,
        f"_last_message_timestamp[{group_id}] populated (got {after!r})",
    )
    _assert(
        before is None or after > before,
        f"timestamp advanced (before={before!r}, after={after!r})",
    )

    # With user_id -> should also bump participation
    resp2 = client.post(
        "/api/track-activity",
        json={"group_id": group_id, "user_id": "user_a"},
    )
    _assert(resp2.status_code == 200, "track-activity with user_id -> 200")
    counts = listener._participation_counts.get(group_id) if hasattr(listener, "_participation_counts") else None
    _assert(
        counts is not None and counts.get("user_a", 0) >= 1,
        f"participation count tracked for user_a (got {counts!r})",
    )

    print("== ai-engine-quality-improvements 2.6 (health reranker_enabled) ==")

    resp_h = client.get("/api/health")
    _assert(
        resp_h.status_code in (200, 503),
        f"health status_code in {{200,503}} (got {resp_h.status_code})",
    )
    body = resp_h.json()
    _assert("reranker_enabled" in body, f"reranker_enabled present in body keys={list(body.keys())}")

    reranker = get_reranker()
    _assert(
        body["reranker_enabled"] == reranker.enabled,
        f"body.reranker_enabled == reranker.enabled (body={body['reranker_enabled']}, runtime={reranker.enabled})",
    )

    print("== add-request-id-correlation (header propagation) ==")

    import uuid as _uuid
    inbound = "12345678-1234-5678-1234-567812345678"

    resp_ra = client.post(
        "/api/track-activity",
        json={"group_id": group_id},
        headers={REQUEST_ID_HEADER: inbound},
    )
    _assert(
        resp_ra.headers.get(REQUEST_ID_HEADER) == inbound,
        f"track-activity echoes inbound X-Request-ID (got {resp_ra.headers.get(REQUEST_ID_HEADER)!r})",
    )

    resp_rh = client.get("/api/health")
    rid_h = resp_rh.headers.get(REQUEST_ID_HEADER)
    _assert(rid_h is not None, f"health response carries X-Request-ID (got {rid_h!r})")
    try:
        _uuid.UUID(rid_h)
        _assert(True, f"health X-Request-ID parses as UUID (got {rid_h})")
    except (ValueError, TypeError):
        _assert(False, f"health X-Request-ID is not a UUID (got {rid_h!r})")

    print("\nAll verifications passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
