"""Dedicated tests for track_activity route (participation branch)."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.track_activity import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_track_activity_with_user_id_tracks_participation():
    mock_listener = MagicMock()
    mock_listener.update_last_message_time = AsyncMock()
    mock_listener.track_participation = AsyncMock()

    with patch(
        "app.api.routes.track_activity.get_logic_listener",
        return_value=mock_listener,
    ):
        resp = client.post(
            "/track-activity",
            json={"group_id": "grp-9", "user_id": "user-7"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"success": True}
    mock_listener.update_last_message_time.assert_awaited_once_with("grp-9")
    mock_listener.track_participation.assert_awaited_once_with("grp-9", "user-7")
