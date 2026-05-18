import pytest
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture(scope="module")
def integration_app():
    @asynccontextmanager
    async def mock_lifespan(app: FastAPI):
        yield

    from app.api.routes import router as api_router

    app = FastAPI(title="Kolabri AI-Engine (Test)", version="1.0.0", lifespan=mock_lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api")
    return app


@pytest.fixture(scope="module")
def client(integration_app) -> TestClient:
    with TestClient(integration_app, raise_server_exceptions=False) as c:
        yield c


class TestEngagementAnalysis:
    def test_analyze_engagement_success(self, client):
        with patch("app.api.routes.analytics.get_engagement_analyzer") as mock_get_analyzer:
            mock_analyzer = MagicMock()
            mock_result = MagicMock()
            mock_result.lexical_variety = 72.5
            mock_result.engagement_type.value = "Cognitive"
            mock_result.is_higher_order = True
            mock_result.hot_indicators = ["mengapa", "analisis"]
            mock_analyzer.analyze_interaction.return_value = mock_result
            mock_get_analyzer.return_value = mock_analyzer

            response = client.post("/api/analytics/engagement", json={
                "text": "Mengapa konsep ini penting? Coba analisis dampaknya.",
            })

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["engagement_type"] == "Cognitive"

    def test_analyze_engagement_empty_text(self, client):
        response = client.post("/api/analytics/engagement", json={"text": ""})
        assert response.status_code in (400, 422)


class TestGroupAnalytics:
    def test_get_group_analytics(self, client):
        with patch("app.api.routes.analytics.get_orchestrator") as mock_get_orch:
            mock_orch = MagicMock()
            mock_orch.get_group_dashboard_data = AsyncMock(return_value={
                "success": True, "group_id": "group-1", "message_count": 50,
                "quality_score": 72,
                "quality_breakdown": {"hot_percentage": 30, "lexical_variety": 65},
                "recommendation": "Diskusi berjalan baik",
                "participants": ["Student A", "Student B"],
                "participant_count": 2,
                "engagement_distribution": {"cognitive": 40, "behavioral": 35, "emotional": 25},
                "hot_percentage": 30,
            })
            mock_get_orch.return_value = mock_orch

            response = client.get("/api/analytics/group/group-1")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["group_id"] == "group-1"


class TestDashboardAnalytics:
    def test_get_group_dashboard_data(self, client):
        with patch("app.api.routes.analytics.get_orchestrator") as mock_get_orch:
            mock_orch = MagicMock()
            mock_orch.get_group_dashboard_data = AsyncMock(return_value={
                "success": True, "group_id": "group-1",
                "message_count": 100, "quality_score": 68,
                "engagement_timeline": [], "participant_stats": {},
            })
            mock_get_orch.return_value = mock_orch

            response = client.get("/api/analytics/dashboard/group/group-1")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_get_individual_dashboard_data(self, client):
        with patch("app.api.routes.analytics.get_orchestrator") as mock_get_orch:
            mock_orch = MagicMock()
            mock_orch.get_individual_dashboard_data = AsyncMock(return_value={
                "success": True, "user_id": "student-1",
                "message_count": 25, "engagement_summary": {},
            })
            mock_get_orch.return_value = mock_orch

            response = client.get("/api/analytics/dashboard/individual/student-1")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
