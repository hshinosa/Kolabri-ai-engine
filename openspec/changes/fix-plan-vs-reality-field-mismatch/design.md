# Design: Fix Plan-vs-Reality Field Mismatch

## Overview

Perbaikan 3 bug yang menyebabkan `plan_vs_reality.py` gagal menganalisis data diskusi:
1. Field mismatch di `_extract_reality()` dan `_extract_plan()`
2. CaseID inconsistency antara Goal_Setting dan reality events
3. NoneType error di `_calculate_time_allocation()`

## Architecture Decision

### Strategi Unifikasi CaseID

**Pilihan A: Gunakan `group_id` untuk semua events** ✅ SELECTED
- Pro: Lebih semantik (group = unit diskusi), sudah dipakai oleh reality events
- Con: Perlu ubah orchestration.py
- Impact: Minimal, hanya 1 line di orchestration.py:453

**Pilihan B: Gunakan `chat_space_id` untuk semua events**
- Pro: Tidak perlu ubah orchestration.py
- Con: Perlu ubah mongodb_logger.py (lebih invasive), less semantic
- Impact: Perlu pass chat_space_id ke semua log_activity calls

**Keputusan**: Pilih A karena lebih clean dan minimal change.

### Backward Compatibility

**Tidak diperlukan** karena:
1. Data lama sudah broken (alignment_score=0)
2. Tidak ada migration path yang feasible
3. Fix hanya berlaku untuk logs baru setelah deploy

## Detailed Changes

### 1. Fix `_extract_plan()` (plan_vs_reality.py:152-212)

**Current**:
```python
goal_events = [
    e for e in events
    if e.get("metadata", {}).get("interactionType") == "GOAL_SETTING"
    or e.get("metadata", {}).get("phase") == "Forethought"
]
```

**Proposed**:
```python
goal_events = [
    e for e in events
    if e.get("Activity") == "Goal_Setting"  # Primary check
    or e.get("metadata", {}).get("interactionType") == "GOAL_SETTING"  # Backward compat
]
```

**Rationale**: 
- Goal_Setting events punya `Activity == "Goal_Setting"` (dari orchestration.py:454)
- Tambahkan backward compat untuk events lama yang masih pakai metadata (jika ada)

### 2. Fix `_extract_reality()` (plan_vs_reality.py:214-267)

**Current**:
```python
performance_events = [
    e for e in events
    if e.get("metadata", {}).get("phase") == "Performance"
    or e.get("metadata", {}).get("interactionType") in ["STUDENT_MESSAGE", "BOT_RESPONSE"]
]
```

**Proposed**:
```python
performance_events = [
    e for e in events
    if e.get("Activity") in ["Student_Message", "Bot_Response"]  # Primary check
    or e.get("metadata", {}).get("interactionType") in ["STUDENT_MESSAGE", "BOT_RESPONSE"]  # Backward compat
]
```

**Rationale**:
- Student_Message/Bot_Response events punya `Activity` field (dari mongodb_logger.py:72)
- Tambahkan backward compat untuk consistency

### 3. Fix `_calculate_time_allocation()` (plan_vs_reality.py:520+)

**Current**: (belum lihat full code, perlu baca dulu)

**Proposed**:
```python
def _calculate_time_allocation(self, goal_events):
    """Calculate time allocation from goal events."""
    if not goal_events:
        return {"total_minutes": 0, "per_goal": []}
    
    # Get timestamps from events
    timestamps = []
    for event in goal_events:
        ts = event.get("Timestamp") or event.get("timestamp")
        if ts:
            timestamps.append(ts)
    
    if len(timestamps) < 2:
        # Fallback: assume 30 min per goal
        return {
            "total_minutes": len(goal_events) * 30,
            "per_goal": [{"goal_id": None, "minutes": 30} for _ in goal_events]
        }
    
    # Calculate duration from first to last timestamp
    try:
        if isinstance(timestamps[0], str):
            timestamps = [datetime.fromisoformat(ts.replace('Z', '+00:00')) for ts in timestamps]
        duration = max(timestamps) - min(timestamps)
        total_minutes = duration.total_seconds() / 60
    except Exception:
        total_minutes = len(goal_events) * 30  # Fallback
    
    return {
        "total_minutes": total_minutes,
        "per_goal": [{"goal_id": None, "minutes": total_minutes / len(goal_events)} for _ in goal_events]
    }
```

**Rationale**:
- Gunakan `Timestamp` field dari event (bukan goal.deadline/created_at yang None)
- Fallback ke 30 min per goal jika tidak cukup data
- Handle ISO format timestamps

### 4. Unify CaseID (orchestration.py:453)

**Current**:
```python
"CaseID": f"{chat_space_id}_session_{session_id}",
```

**Proposed**:
```python
"CaseID": f"{group_id}_session_{session_id}",
```

**Rationale**:
- Gunakan `group_id` untuk consistency dengan reality events
- Perlu pass `group_id` ke validate_goal() (cek caller)

### 5. Update `analyze_session()` Query (plan_vs_reality.py:86-89)

**Current**:
```python
events = await self.mongo_logger.get_activity_logs(
    case_id=chat_space_id,  # <-- Wrong!
    limit=1000
)
```

**Proposed**:
```python
events = await self.mongo_logger.get_activity_logs(
    case_id=f"{group_id}_session_{session_id}",  # Use group_id
    limit=1000
)
```

**Note**: Perlu pass `group_id` dan `session_id` ke `analyze_session()`.

## Testing Strategy

### Unit Tests

**File**: `tests/test_unit/test_plan_vs_reality.py`

**Test Cases**:
1. `test_extract_plan_with_goal_setting_events` - Verify Goal_Setting extraction
2. `test_extract_reality_with_student_bot_events` - Verify Student/Bot extraction
3. `test_compare_plan_reality_alignment` - Verify alignment score > 0
4. `test_calculate_time_allocation_with_timestamps` - Verify time calc from event timestamps
5. `test_case_id_consistency` - Verify both plan and reality use group_id

**Fixtures**: Realistic event structures matching actual logs:
```python
GOAL_SETTING_EVENT = {
    "CaseID": "group123_session_1",
    "Activity": "Goal_Setting",
    "Timestamp": "2026-01-20T10:00:00Z",
    "Resource": "Student_user123",
    "metadata": {"interactionType": "GOAL_SETTING", "phase": "Forethought"},
    "content": "Learn about AI fundamentals",
    "userId": "user123"
}

STUDENT_MESSAGE_EVENT = {
    "CaseID": "group123_session_1",
    "Activity": "Student_Message",
    "Timestamp": "2026-01-20T10:05:00Z",
    "Resource": "Student_user123",
    "Attributes": {
        "original_text": "AI is fascinating because...",
        "srl_object": "Performance",
        "is_hot": True,
        "lexical_variety": 0.75
    }
}
```

### Integration Tests

**Live probe on VPS**:
1. Trigger discussion session with goal setting
2. Query `analyze_session()` with group_id
3. Verify `has_plan=True`, `has_reality=True`, `alignment_score > 0`
4. Check PlanVsDiskusi chart displays data

## Migration & Rollout

### Data Migration
**None required** - old data remains broken, fix applies to new logs only.

### Rollout Plan
1. Deploy to VPS (ai-engine container)
2. Run live probe verification
3. Monitor PlanVsDiskusi chart for new sessions
4. No rollback needed (feature was already broken)

## Dependencies

- **mongodb_logger.py**: No changes needed (already logs correctly)
- **orchestration.py**: Minor change to CaseID (1 line)
- **plan_vs_reality.py**: Main fixes (3 functions)
- **Frontend**: No changes needed (data layer fix only)

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Break existing working features | Very Low | High | Feature already broken, no regression possible |
| Test failures | Low | Medium | Comprehensive fixtures, run tests before deploy |
| CaseID mismatch in edge cases | Low | Medium | Verify with multiple sessions, different group types |
| Performance regression | Very Low | Low | No new queries, same data volume |

## Success Metrics

1. **Functional**: `_extract_reality()` returns `msg_count > 0`
2. **Functional**: `_extract_plan()` returns `has_plan=True` without error
3. **Functional**: `_compare_plan_reality()` returns `alignment_score > 0`
4. **Quality**: All unit tests pass
5. **Integration**: Live probe on VPS succeeds
6. **User-facing**: PlanVsDiskusi chart displays data

## Open Questions

1. **Should we add logging for debug?** - Yes, add `logger.debug()` calls in extract functions
2. **Need to handle timezone in timestamps?** - Yes, use ISO format with timezone awareness
3. **What if group_id is not available?** - Fallback to chat_space_id (defensive coding)
