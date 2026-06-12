"""NFR-PERF-02 task 4.4: analytics dashboard routes use Redis cache."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("redis.asyncio", MagicMock())
sys.modules.setdefault("redis", MagicMock())

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.analytics import router as analytics_router

app = FastAPI()
app.include_router(analytics_router)
client = TestClient(app)


@pytest.fixture
def mock_redis_cache():
    cache = MagicMock()
    cache.generate_key = MagicMock(side_effect=lambda *parts: ":".join(parts))
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    return cache


def test_group_dashboard_cache_miss_then_hit(mock_redis_cache):
    payload = {"group_id": "grp-1", "metrics": {"messages": 3}}

    with (
        patch(
            "app.api.routes.analytics.get_redis_cache",
            new_callable=AsyncMock,
            return_value=mock_redis_cache,
        ),
        patch("app.api.routes.analytics.get_orchestrator") as mock_orch,
    ):
        mock_orch.return_value.get_group_dashboard_data = AsyncMock(
            return_value=payload
        )

        r1 = client.get("/analytics/dashboard/group/grp-1")
        assert r1.status_code == 200
        assert r1.json() == payload
        mock_orch.return_value.get_group_dashboard_data.assert_called_once()

        mock_redis_cache.get = AsyncMock(return_value=payload)
        r2 = client.get("/analytics/dashboard/group/grp-1")
        assert r2.status_code == 200
        assert r2.json() == payload
        assert mock_orch.return_value.get_group_dashboard_data.call_count == 1


def test_group_dashboard_serves_cached_without_orchestrator(mock_redis_cache):
    cached = {"group_id": "grp-2", "cached": True}
    mock_redis_cache.get = AsyncMock(return_value=cached)

    with (
        patch(
            "app.api.routes.analytics.get_redis_cache",
            new_callable=AsyncMock,
            return_value=mock_redis_cache,
        ),
        patch("app.api.routes.analytics.get_orchestrator") as mock_orch,
    ):
        response = client.get("/analytics/dashboard/group/grp-2")
        assert response.status_code == 200
        assert response.json() == cached
        mock_orch.return_value.get_group_dashboard_data.assert_not_called()
