"""Independent black-box API tests for the real FastAPI app."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app


def _assert_json_error_structure(response, expected_status: int | None = None) -> dict:
    if expected_status is not None:
        assert response.status_code == expected_status

    assert "application/json" in response.headers.get("content-type", "")
    data = response.json()
    assert isinstance(data, dict)
    assert "detail" in data
    assert "message" in data
    assert isinstance(data["detail"], str)
    assert isinstance(data["message"], str)
    assert data["message"]
    return data


def _assert_success_or_sanitized_server_error(response, allowed_statuses: set[int]) -> None:
    assert response.status_code in allowed_statuses
    if response.status_code >= 500:
        _assert_json_error_structure(response, response.status_code)


class TestAppImport:
    def test_main_exports_fastapi_app(self):
        assert app is not None
        assert hasattr(app, "router")


class TestAuthMiddleware:
    def test_health_requires_authorization_header(self, client: TestClient):
        response = client.get("/api/health")

        data = _assert_json_error_structure(response, 401)
        assert data["detail"] == "REQUEST_ERROR"
        assert "Authorization header required" in data["message"]

    def test_health_rejects_malformed_authorization_header(
        self, client: TestClient, malformed_auth_headers: dict[str, str]
    ):
        response = client.get("/api/health", headers=malformed_auth_headers)

        data = _assert_json_error_structure(response, 401)
        assert data["detail"] == "REQUEST_ERROR"
        assert "Invalid authorization format" in data["message"]

    def test_health_rejects_wrong_auth_scheme(
        self, client: TestClient, wrong_scheme_headers: dict[str, str]
    ):
        response = client.get("/api/health", headers=wrong_scheme_headers)

        data = _assert_json_error_structure(response, 401)
        assert data["detail"] == "REQUEST_ERROR"
        assert "Invalid authentication scheme" in data["message"]

    def test_health_rejects_invalid_api_key(
        self, client: TestClient, invalid_auth_headers: dict[str, str]
    ):
        response = client.get("/api/health", headers=invalid_auth_headers)

        data = _assert_json_error_structure(response, 403)
        assert data["detail"] == "REQUEST_ERROR"
        assert "Invalid credentials" in data["message"]

    def test_valid_auth_reaches_endpoint(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.get("/api/health", headers=auth_headers)

        assert response.status_code == 200


class TestHealthAndMonitoringEndpoints:
    def test_health_check_returns_status(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.get("/api/health", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_health_check_returns_expected_structure(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.get("/api/health", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) >= {"status", "version", "timestamp", "services"}
        assert data["status"] in {"healthy", "degraded", "unhealthy"}
        assert isinstance(data["services"], dict)
        assert "vector_store" in data["services"]
        assert "llm" in data["services"]

    def test_circuit_breaker_endpoint_returns_monitoring_payload(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.get("/api/health/circuit-breakers", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "llm_service" in data

    def test_circuit_breaker_endpoint_returns_json(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.get("/api/health/circuit-breakers", headers=auth_headers)

        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")

    def test_reranker_health_endpoint_responds(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.get("/api/health/reranker", headers=auth_headers)

        assert response.status_code in {200, 500}
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
        else:
            _assert_json_error_structure(response, 500)

    def test_metrics_endpoint_returns_prometheus_like_text(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.get("/api/metrics", headers=auth_headers)

        assert response.status_code == 200
        assert isinstance(response.text, str)
        assert response.text is not None

    def test_metrics_endpoint_returns_text_content_type(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.get("/api/metrics", headers=auth_headers)

        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert any(kind in content_type for kind in ("text/plain", "text/", "application/openmetrics-text"))

    def test_monitoring_health_endpoint_returns_json(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.get("/api/health/monitoring", headers=auth_headers)

        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")

    def test_cache_statistics_endpoint_returns_200(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.get("/api/efficiency/cache/statistics", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "enabled" in data

    def test_efficiency_statistics_endpoint_returns_200(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.get("/api/efficiency/statistics", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "enabled" in data

    def test_rate_limit_info_endpoint_returns_200(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.get("/api/efficiency/rate-limit/test-blackbox", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "enabled" in data


class TestRequestValidation:
    def test_ask_rejects_empty_body(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.post("/api/ask", headers=auth_headers)

        _assert_json_error_structure(response, 422)

    def test_ask_rejects_missing_query(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.post(
            "/api/ask",
            headers=auth_headers,
            json={"course_id": "test-course"},
        )

        _assert_json_error_structure(response, 422)

    def test_personal_chat_rejects_empty_body(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.post("/api/chat/personal", headers=auth_headers)

        _assert_json_error_structure(response, 422)

    def test_ingest_rejects_missing_file_and_form_fields(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.post("/api/ingest", headers=auth_headers, data={})

        _assert_json_error_structure(response, 422)

    def test_goal_validate_rejects_empty_body(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.post("/api/goals/validate", headers=auth_headers)

        _assert_json_error_structure(response, 422)

    def test_goal_refine_rejects_empty_body(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.post("/api/goals/refine", headers=auth_headers)

        _assert_json_error_structure(response, 422)

    def test_engagement_analysis_rejects_empty_body(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.post("/api/analytics/engagement", headers=auth_headers)

        _assert_json_error_structure(response, 422)

    def test_intervention_analyze_rejects_empty_body(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.post("/api/intervention/analyze", headers=auth_headers)

        _assert_json_error_structure(response, 422)

    def test_intervention_summary_rejects_empty_body(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.post("/api/intervention/summary", headers=auth_headers)

        _assert_json_error_structure(response, 422)

    def test_intervention_prompt_rejects_empty_body(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.post("/api/intervention/prompt", headers=auth_headers)

        _assert_json_error_structure(response, 422)

    def test_chat_rejects_empty_body(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.post("/api/chat", headers=auth_headers)

        _assert_json_error_structure(response, 422)


class TestValidRequestsWithoutBackends:
    def test_ask_accepts_valid_request_shape(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.post(
            "/api/ask",
            headers=auth_headers,
            json={"query": "Apa itu React?", "course_id": "test-course"},
        )

        _assert_success_or_sanitized_server_error(response, {200, 500})
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
            assert set(data.keys()) >= {"answer", "success"}

    def test_goal_validate_accepts_valid_form_request_shape(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.post(
            "/api/goals/validate",
            headers=auth_headers,
            data={
                "goal_text": "Membuat 5 halaman laporan dalam 3 hari",
                "user_id": "user-1",
                "chat_space_id": "space-1",
            },
        )

        _assert_success_or_sanitized_server_error(response, {200, 500})
        if response.status_code == 200:
            assert isinstance(response.json(), dict)

    def test_group_status_endpoint_does_not_crash(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.get("/api/groups/test-group/status", headers=auth_headers)

        _assert_success_or_sanitized_server_error(response, {200, 500})
        if response.status_code == 200:
            assert isinstance(response.json(), dict)

    def test_delete_document_endpoint_does_not_crash(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.delete("/api/documents/nonexistent", headers=auth_headers)

        _assert_success_or_sanitized_server_error(response, {200, 500})
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
            assert "success" in data


class TestResponseStructure:
    def test_validation_errors_use_consistent_structure(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.post("/api/ask", headers=auth_headers, json={})

        data = _assert_json_error_structure(response, 422)
        assert data["detail"] == "VALIDATION_ERROR"

    def test_auth_errors_use_consistent_structure(self, client: TestClient):
        response = client.get("/api/health")

        data = _assert_json_error_structure(response, 401)
        assert data["detail"] == "REQUEST_ERROR"

    def test_invalid_auth_key_uses_consistent_structure(
        self, client: TestClient, invalid_auth_headers: dict[str, str]
    ):
        response = client.get("/api/health", headers=invalid_auth_headers)

        data = _assert_json_error_structure(response, 403)
        assert data["detail"] == "REQUEST_ERROR"

    def test_internal_errors_are_sanitized_when_they_happen(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.delete("/api/documents/nonexistent", headers=auth_headers)

        if response.status_code == 500:
            data = _assert_json_error_structure(response, 500)
            assert data["detail"] in {"REQUEST_ERROR", "INTERNAL_SERVER_ERROR"}
        else:
            assert response.status_code == 200

    def test_health_response_is_json(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.get("/api/health", headers=auth_headers)

        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")

    def test_successful_ask_response_shape_when_available(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        response = client.post(
            "/api/ask",
            headers=auth_headers,
            json={"query": "Halo AI", "course_id": "test-course"},
        )

        assert response.status_code in {200, 500}
        if response.status_code == 200:
            data = response.json()
            assert "answer" in data
            assert "success" in data
            assert isinstance(data["success"], bool)
        else:
            _assert_json_error_structure(response, 500)
