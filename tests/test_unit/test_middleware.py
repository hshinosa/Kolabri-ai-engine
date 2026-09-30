from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.config import settings
from app.middleware.auth import (
    optional_auth,
    require_auth,
    validate_api_key,
)
from app.middleware.request_size_limit import LimitRequestSizeMiddleware


TEST_SECRET = "test-core-secret"
LONG_VALID_KEY = "test-core-secret-extra-long"
MASKED_TEST_SECRET = TEST_SECRET[:10] + "..."


def make_mock_request(
    authorization=None,
    method="GET",
    path="http://testserver/middleware",
    client_host="127.0.0.1",
    include_client=True,
):
    headers = {}
    if authorization is not None:
        headers["Authorization"] = authorization

    request = MagicMock()
    request.headers = headers
    request.method = method
    request.url = path
    request.client = SimpleNamespace(host=client_host) if include_client else None
    return request


def create_size_limit_app(max_size_bytes=1024):
    app = FastAPI()
    app.add_middleware(LimitRequestSizeMiddleware, max_size_bytes=max_size_bytes)

    @app.post("/payload")
    async def post_payload(request: Request):
        body = await request.body()
        return {"method": request.method, "length": len(body), "body": body.decode("utf-8")}

    @app.put("/payload")
    async def put_payload(request: Request):
        body = await request.body()
        return {"method": request.method, "length": len(body)}

    @app.patch("/payload")
    async def patch_payload(request: Request):
        body = await request.body()
        return {"method": request.method, "length": len(body)}

    @app.get("/payload")
    async def get_payload():
        return {"method": "GET", "ok": True}

    return app


class TestValidateApiKey:
    @pytest.mark.unit
    def test_validate_api_key_returns_true_for_valid_key(self):
        with patch.object(settings, "CORE_API_SECRET", TEST_SECRET):
            assert validate_api_key(TEST_SECRET) is True

    @pytest.mark.unit
    def test_validate_api_key_returns_false_for_empty_string(self):
        with patch("app.middleware.auth.hmac.compare_digest") as mock_compare:
            assert validate_api_key("") is False
            mock_compare.assert_not_called()

    @pytest.mark.unit
    def test_validate_api_key_returns_false_for_none(self):
        with patch("app.middleware.auth.hmac.compare_digest") as mock_compare:
            assert validate_api_key(None) is False
            mock_compare.assert_not_called()

    @pytest.mark.unit
    def test_validate_api_key_returns_false_for_wrong_key(self):
        with patch.object(settings, "CORE_API_SECRET", TEST_SECRET):
            assert validate_api_key("wrong-secret") is False

    @pytest.mark.unit
    def test_validate_api_key_uses_compare_digest(self):
        with patch.object(settings, "CORE_API_SECRET", TEST_SECRET), patch(
            "app.middleware.auth.hmac.compare_digest", return_value=True
        ) as mock_compare:
            assert validate_api_key(TEST_SECRET) is True
            mock_compare.assert_called_once_with(TEST_SECRET, TEST_SECRET)


class TestRequireAuth:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_require_auth_raises_401_without_header(self):
        request = make_mock_request()

        with pytest.raises(Exception) as exc_info:
            await require_auth(request)

        exc = exc_info.value
        assert exc.status_code == 401
        assert "Authorization header required" in exc.detail
        assert exc.headers == {"WWW-Authenticate": "Bearer"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_require_auth_raises_401_for_single_token_format(self):
        request = make_mock_request(authorization="onlytoken")

        with pytest.raises(Exception) as exc_info:
            await require_auth(request)

        exc = exc_info.value
        assert exc.status_code == 401
        assert "Invalid authorization format" in exc.detail

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_require_auth_raises_401_for_three_part_format(self):
        request = make_mock_request(authorization="Bearer too many parts")

        with pytest.raises(Exception) as exc_info:
            await require_auth(request)

        exc = exc_info.value
        assert exc.status_code == 401
        assert "Invalid authorization format" in exc.detail

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_require_auth_raises_401_for_wrong_scheme(self):
        request = make_mock_request(authorization=f"Basic {TEST_SECRET}")

        with pytest.raises(Exception) as exc_info:
            await require_auth(request)

        exc = exc_info.value
        assert exc.status_code == 401
        assert "Invalid authentication scheme" in exc.detail

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_require_auth_accepts_case_insensitive_bearer_scheme(self):
        request = make_mock_request(authorization=f"BEARER {TEST_SECRET}")

        with patch.object(settings, "CORE_API_SECRET", TEST_SECRET):
            result = await require_auth(request)

        assert result == {"authenticated": True, "api_key": MASKED_TEST_SECRET}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_require_auth_raises_403_for_invalid_key(self):
        request = make_mock_request(authorization="Bearer wrong-secret")

        with patch.object(settings, "CORE_API_SECRET", TEST_SECRET):
            with pytest.raises(Exception) as exc_info:
                await require_auth(request)

        exc = exc_info.value
        assert exc.status_code == 403
        assert exc.detail == "Invalid credentials"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_require_auth_returns_success_for_valid_key(self):
        request = make_mock_request(authorization=f"Bearer {TEST_SECRET}", method="POST")

        with patch.object(settings, "CORE_API_SECRET", TEST_SECRET):
            result = await require_auth(request)

        assert result == {"authenticated": True, "api_key": MASKED_TEST_SECRET}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_require_auth_masks_long_api_key_in_response(self):
        request = make_mock_request(authorization=f"Bearer {LONG_VALID_KEY}")

        with patch.object(settings, "CORE_API_SECRET", LONG_VALID_KEY):
            result = await require_auth(request)

        assert result == {"authenticated": True, "api_key": LONG_VALID_KEY[:10] + "..."}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_require_auth_logs_unknown_ip_when_client_missing(self):
        request = make_mock_request(include_client=False)

        with patch("app.middleware.auth.logger.warning") as mock_warning:
            with pytest.raises(Exception):
                await require_auth(request)

        _, kwargs = mock_warning.call_args
        assert kwargs["ip"] == "unknown"


class TestOptionalAuth:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_optional_auth_returns_true_for_valid_auth(self):
        request = make_mock_request(authorization=f"Bearer {TEST_SECRET}")

        with patch.object(settings, "CORE_API_SECRET", TEST_SECRET):
            result = await optional_auth(request)

        assert result == {"authenticated": True}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_optional_auth_returns_false_for_invalid_key(self):
        request = make_mock_request(authorization="Bearer wrong-secret")

        with patch.object(settings, "CORE_API_SECRET", TEST_SECRET):
            result = await optional_auth(request)

        assert result == {"authenticated": False}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_optional_auth_returns_false_when_header_missing(self):
        request = make_mock_request()

        result = await optional_auth(request)

        assert result == {"authenticated": False}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_optional_auth_returns_false_for_invalid_format(self):
        request = make_mock_request(authorization="Bearer")

        result = await optional_auth(request)

        assert result == {"authenticated": False}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_optional_auth_returns_false_for_wrong_scheme(self):
        request = make_mock_request(authorization=f"Basic {TEST_SECRET}")

        with patch.object(settings, "CORE_API_SECRET", TEST_SECRET):
            result = await optional_auth(request)

        assert result == {"authenticated": False}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_optional_auth_accepts_case_insensitive_scheme(self):
        request = make_mock_request(authorization=f"bEaReR {TEST_SECRET}")

        with patch.object(settings, "CORE_API_SECRET", TEST_SECRET):
            result = await optional_auth(request)

        assert result == {"authenticated": True}


class TestLimitRequestSizeMiddleware:
    @pytest.mark.unit
    def test_limit_request_size_middleware_stores_default_limit(self):
        app = create_size_limit_app()
        middleware = LimitRequestSizeMiddleware(app)

        assert middleware.max_size_bytes == 10 * 1024 * 1024

    @pytest.mark.unit
    def test_post_under_limit_passes_through(self):
        client = TestClient(create_size_limit_app(max_size_bytes=10))

        response = client.post("/payload", content=b"12345")

        assert response.status_code == 200
        assert response.json()["length"] == 5
        assert response.json()["body"] == "12345"

    @pytest.mark.unit
    def test_post_over_limit_returns_413(self):
        client = TestClient(create_size_limit_app(max_size_bytes=4))

        response = client.post("/payload", content=b"12345")

        assert response.status_code == 413
        assert response.json() == {
            "detail": "PAYLOAD_TOO_LARGE",
            "message": "Request body exceeds maximum size of 4 bytes",
        }

    @pytest.mark.unit
    def test_post_exactly_at_limit_passes_through(self):
        client = TestClient(create_size_limit_app(max_size_bytes=5))

        response = client.post("/payload", content=b"12345")

        assert response.status_code == 200
        assert response.json()["length"] == 5

    @pytest.mark.unit
    def test_get_request_skips_body_check(self):
        client = TestClient(create_size_limit_app(max_size_bytes=1))

        response = client.get("/payload")

        assert response.status_code == 200
        assert response.json() == {"method": "GET", "ok": True}

    @pytest.mark.unit
    def test_put_request_under_limit_passes_through(self):
        client = TestClient(create_size_limit_app(max_size_bytes=6))

        response = client.put("/payload", content=b"12345")

        assert response.status_code == 200
        assert response.json() == {"method": "PUT", "length": 5}

    @pytest.mark.unit
    def test_put_request_over_limit_returns_413(self):
        client = TestClient(create_size_limit_app(max_size_bytes=3))

        response = client.put("/payload", content=b"12345")

        assert response.status_code == 413
        assert response.json()["detail"] == "PAYLOAD_TOO_LARGE"

    @pytest.mark.unit
    def test_patch_request_under_limit_passes_through(self):
        client = TestClient(create_size_limit_app(max_size_bytes=8))

        response = client.patch("/payload", content=b"1234567")

        assert response.status_code == 200
        assert response.json() == {"method": "PATCH", "length": 7}

    @pytest.mark.unit
    def test_patch_request_over_limit_returns_413(self):
        client = TestClient(create_size_limit_app(max_size_bytes=2))

        response = client.patch("/payload", content=b"123")

        assert response.status_code == 413
        assert "maximum size of 2 bytes" in response.json()["message"]

    @pytest.mark.unit
    def test_custom_max_size_bytes_is_respected(self):
        custom_limit = 12
        client = TestClient(create_size_limit_app(max_size_bytes=custom_limit))

        response = client.post("/payload", content=b"1234567890123")

        assert response.status_code == 413
        assert str(custom_limit) in response.json()["message"]

    @pytest.mark.unit
    def test_empty_post_body_passes_through(self):
        client = TestClient(create_size_limit_app(max_size_bytes=1))

        response = client.post("/payload", content=b"")

        assert response.status_code == 200
        assert response.json()["length"] == 0
