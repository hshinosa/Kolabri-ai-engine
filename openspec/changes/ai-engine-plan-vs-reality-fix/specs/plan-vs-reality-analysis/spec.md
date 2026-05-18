## plan-vs-reality-analysis (Fix)

### Requirements

#### REQ-PVR-01: validate_goal() Log Format

`validate_goal()` di `orchestration.py` harus menambahkan log kedua setelah log `Goal_Validation` yang sudah ada:
```python
await self.mongo_logger.log_activity({
    "CaseID": f"{chat_space_id}_session_{session_id}",
    "Activity": "Goal_Setting",
    "metadata": {"interactionType": "GOAL_SETTING", "phase": "Forethought"},
    "content": goal_text,
    "userId": user_id,
})
```
Log pertama (`Activity: "Goal_Validation"`) tetap tidak diubah.

#### REQ-PVR-02: get_group_analytics() Session ID Dinamis

`get_group_analytics()` harus menggunakan session ID aktual, bukan hardcoded `session_1`:
```python
session_id = await self._get_latest_session_id(group_id)
case_id = f"{group_id}_session_{session_id}"
```

#### REQ-PVR-03: Backward Compatibility

Tidak ada perubahan pada format log yang sudah ada. Hanya penambahan log baru dan perbaikan session ID.
