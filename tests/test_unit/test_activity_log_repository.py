from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.repositories import ActivityLogRepository


@pytest.fixture
def fake_db():
    db = MagicMock()
    db.activity_logs.find_one = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_get_latest_session_for_group_extracts_id(fake_db):
    fake_db.activity_logs.find_one.return_value = {"CaseID": "group_42_session_3"}
    repo = ActivityLogRepository(fake_db)
    assert await repo.get_latest_session_for_group("group_42") == "3"


@pytest.mark.asyncio
async def test_get_latest_session_returns_none_when_empty(fake_db):
    fake_db.activity_logs.find_one.return_value = None
    repo = ActivityLogRepository(fake_db)
    assert await repo.get_latest_session_for_group("group_42") is None


@pytest.mark.asyncio
async def test_get_last_intervention_passes_query(fake_db):
    fake_db.activity_logs.find_one.return_value = {"Timestamp": datetime.utcnow()}
    repo = ActivityLogRepository(fake_db)
    await repo.get_last_intervention_for_group("group_42")
    args, kwargs = fake_db.activity_logs.find_one.call_args
    assert args[0]["Activity"]["$regex"] == "^System_Intervention"
    assert "group_42" in args[0]["CaseID"]["$regex"]


@pytest.mark.asyncio
async def test_get_first_student_message_after_filters_by_timestamp(fake_db):
    ts = datetime.utcnow()
    fake_db.activity_logs.find_one.return_value = {"Activity": "Student_Message"}
    repo = ActivityLogRepository(fake_db)
    await repo.get_first_student_message_after("group_42", ts)
    args, _ = fake_db.activity_logs.find_one.call_args
    assert args[0]["Timestamp"]["$gt"] == ts
    assert args[0]["Activity"] == "Student_Message"


@pytest.mark.asyncio
async def test_returns_none_when_db_is_none():
    repo = ActivityLogRepository(None)
    assert await repo.get_latest_session_for_group("g") is None
    assert await repo.get_last_intervention_for_group("g") is None
    assert await repo.get_first_student_message_after("g", datetime.utcnow()) is None
