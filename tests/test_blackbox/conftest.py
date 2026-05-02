"""Black-box API test fixtures using the real FastAPI app."""

from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
import app.services.monitoring as monitoring
from main import app


@asynccontextmanager
async def _test_lifespan(_app):
    """Disable startup side effects for HTTP black-box tests."""
    yield


@pytest.fixture(scope="session")
def auth_headers() -> dict[str, str]:
    secret = settings.CORE_API_SECRET or "shared-secret-key"
    return {"Authorization": f"Bearer {secret}"}


@pytest.fixture(scope="session")
def invalid_auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer definitely-invalid-secret"}


@pytest.fixture(scope="session")
def malformed_auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer"}


@pytest.fixture(scope="session")
def wrong_scheme_headers() -> dict[str, str]:
    return {"Authorization": "Basic shared-secret-key"}


@pytest.fixture(scope="session")
def client() -> TestClient:
    monitoring.CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    monitoring.generate_latest = lambda: b"# blackbox_test_metric 1\n"
    monitoring._monitor = None
    app.router.lifespan_context = _test_lifespan
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
