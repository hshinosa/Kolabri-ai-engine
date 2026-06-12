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

    app = FastAPI(
        title="Kolabri AI-Engine (Test)", version="1.0.0", lifespan=mock_lifespan
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api")
    return app


@pytest.fixture(scope="module")
def client(integration_app) -> TestClient:
    with TestClient(integration_app, raise_server_exceptions=False) as c:
        yield c


class TestGoalValidation:
    def test_validate_valid_bloom_goal(self, client):
        with patch("app.api.routes.goals.get_orchestrator") as mock_get_orch:
            mock_orch = MagicMock()
            mock_orch.validate_goal = AsyncMock(
                return_value={
                    "is_valid": True,
                    "score": 85,
                    "feedback": "Goal sudah baik",
                    "socratic_hint": None,
                    "missing_criteria": [],
                    "details": {"bloom_level": "C4"},
                    "success": True,
                }
            )
            mock_get_orch.return_value = mock_orch

            response = client.post(
                "/api/goals/validate",
                data={
                    "goal_text": "Menganalisis dampak perubahan iklim terhadap ekosistem laut",
                    "user_id": "student-1",
                    "chat_space_id": "cs-1",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["is_valid"] is True

    def test_validate_invalid_goal_returns_feedback(self, client):
        with patch("app.api.routes.goals.get_orchestrator") as mock_get_orch:
            mock_orch = MagicMock()
            mock_orch.validate_goal = AsyncMock(
                return_value={
                    "is_valid": False,
                    "score": 30,
                    "feedback": "Goal belum menggunakan kata kerja Bloom tingkat tinggi",
                    "socratic_hint": "Coba gunakan kata kerja seperti 'menganalisis'",
                    "missing_criteria": ["higher_order_verb"],
                    "details": {},
                    "success": True,
                }
            )
            mock_get_orch.return_value = mock_orch

            response = client.post(
                "/api/goals/validate",
                data={
                    "goal_text": "Belajar tentang iklim",
                    "user_id": "student-1",
                    "chat_space_id": "cs-1",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["is_valid"] is False
            assert data["socratic_hint"] is not None

    def test_validate_missing_goal_text_returns_validation_result(self, client):
        """Form tanpa goal_text: API mengembalikan 200 dengan is_valid=False (bukan 422)."""
        response = client.post(
            "/api/goals/validate",
            data={
                "user_id": "student-1",
                "chat_space_id": "cs-1",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is False


class TestGoalRefinement:
    def test_refine_goal_success(self, client):
        with patch("app.api.routes.goals.get_orchestrator") as mock_get_orch:
            mock_orch = MagicMock()
            mock_orch.get_goal_refinement = AsyncMock(
                return_value={
                    "success": True,
                    "refined_goal": "Mengevaluasi dampak perubahan iklim terhadap biodiversitas laut",
                    "explanation": "Goal diperbaiki dengan kata kerja Bloom C5",
                    "suggestions": ["Tambahkan konteks spesifik"],
                    "validation": {"is_valid": True, "score": 90},
                    "tokens_used": 150,
                }
            )
            mock_get_orch.return_value = mock_orch

            response = client.post(
                "/api/goals/refine",
                data={
                    "current_goal": "Belajar tentang iklim",
                    "missing_criteria": '["higher_order_verb", "specificity"]',
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "refined_goal" in data

    def test_refine_missing_fields_returns_422(self, client):
        response = client.post("/api/goals/refine", data={})
        assert response.status_code == 422
