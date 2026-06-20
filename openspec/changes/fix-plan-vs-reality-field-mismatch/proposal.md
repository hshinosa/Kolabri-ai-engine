# Proposal: Fix Plan-vs-Reality Field Mismatch

## Problem Statement

The `plan_vs_reality.py` service fails to extract and analyze discussion data due to field mismatches between:
1. **Goal_Setting events** (logged by orchestration.py) - uses `metadata.interactionType`, `metadata.phase`, `content`, `userId`
2. **Student_Message/Bot_Response events** (logged by mongodb_logger.py) - uses `Attributes.original_text`, `Attributes.srl_object`, NO metadata object
3. **CaseID mismatch** - Goal_Setting uses `chat_space_id`, reality events use `group_id`, making them unqueryable together

## Symptoms

- `_extract_reality()` returns `has_reality=False, msg_count=0`
- `_extract_plan()` crashes with `TypeError: unsupported operand type(s) for -: 'NoneType' and 'NoneType'`
- `_compare_plan_reality()` returns `alignment_score=0.0`
- PlanVsDiskusi chart shows no data

## Root Causes

### 1. Field Schema Mismatch in `_extract_reality()`

**Current code** (plan_vs_reality.py:221-225):
```python
performance_events = [
    e for e in events
    if e.get("metadata", {}).get("phase") == "Performance"
    or e.get("metadata", {}).get("interactionType") in ["STUDENT_MESSAGE", "BOT_RESPONSE"]
]
```

**Problem**: Student_Message and Bot_Response events use `Activity` field, not `metadata.interactionType`

**Actual event structure**:
```python
{
    "CaseID": "group123_session_1",
    "Activity": "Student_Message",  # <-- Use this!
    "Timestamp": "2026-01-20T10:00:00Z",
    "Resource": "Student_user123",
    "Attributes": {
        "original_text": "Discussion content",
        "srl_object": "Performance",
        "is_hot": True,
        "lexical_variety": 0.75
    }
}
```

### 2. CaseID Inconsistency

**Goal_Setting** (orchestration.py:453):
```python
"CaseID": f"{chat_space_id}_session_{session_id}"
```

**Reality events** (mongodb_logger.py + orchestration.py):
```python
"CaseID": f"{group_id}_session_{session_id}"
```

Since `chat_space_id ≠ group_id`, queries can't find both plan and reality together.

### 3. NoneType Error in `_calculate_time_allocation()`

**Current code** tries to calculate duration from `goal.deadline - goal.created_at` when both are None, causing TypeError.

## Proposed Solution

### Fix 1: Update `_extract_reality()` to use `Activity` field

```python
performance_events = [
    e for e in events
    if e.get("Activity") in ["Student_Message", "Bot_Response"]
]
```

### Fix 2: Unify CaseID strategy

**Option A**: Use `group_id` for both (recommended - more semantic)
- Update orchestration.py:453 to use `group_id` instead of `chat_space_id`

**Option B**: Use `chat_space_id` for both
- Update mongodb_logger.py to accept and use `chat_space_id`

**Decision**: Use Option A - group_id is more semantic and already used by reality events.

### Fix 3: Add null checks in `_calculate_time_allocation()`

```python
if goal.deadline and goal.created_at:
    duration = goal.deadline - goal.created_at
    # ... rest of calculation
else:
    # Fallback: use event timestamps
    # ... 
```

## Scope

### In Scope
- Fix `_extract_reality()` field filtering
- Fix `_extract_plan()` to also use `Activity` field for Goal_Setting
- Unify CaseID to use `group_id` consistently
- Add null checks for time calculations
- Update unit tests with realistic event fixtures
- Verify with live probe on VPS

### Out of Scope
- Changing event logging schema (too invasive)
- Adding new analytics features
- Modifying frontend PlanVsDiskusi component (only data layer)

## Implementation Tasks

### ✅ Completed (Field Mapping Fixes)
1. **Fix `_extract_reality()`** - Update filter to use `Activity` field ✅
2. **Fix `_extract_plan()`** - Update filter to use `Activity == "Goal_Setting"` ✅
3. **Fix `_calculate_time_allocation()`** - Add null checks, use event timestamps as fallback ✅
4. **Add unit tests** - Create realistic event fixtures matching actual log structure ✅ (22 tests, all passing)

### ⏸️ Deferred (CaseID Unification)
5. **Unify CaseID** - Change orchestration.py:453 to use `group_id`
   - **Reason**: Requires signature change to `validate_goal` and updates to all callers
   - **Impact**: Feature still works with current fixes, but requires manual CaseID alignment
   - **Priority**: Low - can be done in follow-up PR
   - **Effort**: 2-3 hours
6. **Verify on VPS** - Run live probe, check PlanVsDiskusi chart
   - **Status**: Paused by user request - deployment decision pending

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Breaking existing queries | High | Add backward compatibility - check both old and new field names |
| Data migration needed | Medium | No migration - fix applies to new logs only, old data remains broken (acceptable) |
| Test coverage gaps | Low | Add comprehensive fixtures covering all event types |

## Success Criteria

- [ ] `_extract_reality()` returns `has_reality=True` with correct message count
- [ ] `_extract_plan()` returns `has_plan=True` without TypeError
- [ ] `_compare_plan_reality()` returns `alignment_score > 0` for matching plan/reality
- [ ] Unit tests pass with realistic event fixtures
- [ ] Live probe on VPS shows non-zero alignment score
- [ ] PlanVsDiskusi chart displays data (frontend integration)

## Timeline Estimate

- Design & spec: 30 min
- Implementation: 1 hour
- Testing: 30 min
- Verification: 30 min
- **Total: 2.5 hours**
