from __future__ import annotations

from typing import Any, List, Optional


class ActivityLogRepository:
    """Thin async repository for the `activity_logs` collection."""

    def __init__(self, db: Any) -> None:
        self._db = db

    async def get_latest_session_for_group(self, group_id: str) -> Optional[str]:
        if self._db is None:
            return None
        latest = await self._db.activity_logs.find_one(
            {"CaseID": {"$regex": f"^{group_id}_session_"}},
            sort=[("Timestamp", -1)],
        )
        if not latest:
            return None
        return latest["CaseID"].split("_session_")[-1]

    async def get_last_intervention_for_group(self, group_id: str) -> Optional[dict]:
        if self._db is None:
            return None
        return await self._db.activity_logs.find_one(
            {
                "CaseID": {"$regex": f"^{group_id}"},
                "Activity": {"$regex": "^System_Intervention"},
            },
            sort=[("Timestamp", -1)],
        )

    async def get_first_student_message_after(
        self, group_id: str, timestamp: Any
    ) -> Optional[dict]:
        if self._db is None:
            return None
        return await self._db.activity_logs.find_one(
            {
                "CaseID": {"$regex": f"^{group_id}"},
                "Activity": "Student_Message",
                "Timestamp": {"$gt": timestamp},
            },
            sort=[("Timestamp", 1)],
        )

    async def list_student_messages_for_group(self, group_id: str) -> List[dict]:
        if self._db is None:
            return []
        cursor = self._db.activity_logs.find(
            {"CaseID": {"$regex": f"^{group_id}"}, "Activity": "Student_Message"}
        )
        return await cursor.to_list(length=None)

    async def list_student_messages_for_case(self, case_id: str) -> List[dict]:
        if self._db is None:
            return []
        cursor = self._db.activity_logs.find(
            {"CaseID": case_id, "Activity": "Student_Message"}
        )
        return await cursor.to_list(length=None)

    async def list_student_messages_for_group_sorted(
        self, group_id: str
    ) -> List[dict]:
        if self._db is None:
            return []
        cursor = self._db.activity_logs.find(
            {"CaseID": {"$regex": f"^{group_id}"}, "Activity": "Student_Message"}
        ).sort([("Resource", 1), ("Timestamp", 1)])
        return await cursor.to_list(length=None)
