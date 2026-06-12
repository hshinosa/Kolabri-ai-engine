"""Additional coverage for ActivityLogRepository list/cursor paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.repositories import ActivityLogRepository


def _cursor(docs: list):
    cur = MagicMock()
    cur.to_list = AsyncMock(return_value=docs)
    cur.sort = MagicMock(return_value=cur)
    return cur


@pytest.mark.asyncio
async def test_list_student_messages_for_group():
    db = MagicMock()
    db.activity_logs.find = MagicMock(
        return_value=_cursor([{"Activity": "Student_Message"}])
    )
    repo = ActivityLogRepository(db)
    rows = await repo.list_student_messages_for_group("g1")
    assert len(rows) == 1
    db.activity_logs.find.assert_called_once()


@pytest.mark.asyncio
async def test_list_student_messages_for_case():
    db = MagicMock()
    db.activity_logs.find = MagicMock(return_value=_cursor([]))
    repo = ActivityLogRepository(db)
    assert await repo.list_student_messages_for_case("case_9") == []


@pytest.mark.asyncio
async def test_list_student_messages_for_group_sorted_uses_sort():
    db = MagicMock()
    cur = _cursor([{"a": 1}])
    db.activity_logs.find = MagicMock(return_value=cur)
    repo = ActivityLogRepository(db)
    await repo.list_student_messages_for_group_sorted("g2")
    cur.sort.assert_called_once_with([("Resource", 1), ("Timestamp", 1)])


@pytest.mark.asyncio
async def test_list_methods_return_empty_when_db_none():
    repo = ActivityLogRepository(None)
    assert await repo.list_student_messages_for_group("g") == []
    assert await repo.list_student_messages_for_case("c") == []
    assert await repo.list_student_messages_for_group_sorted("g") == []
