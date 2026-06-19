# Spec: Unify CaseID Between Plan and Reality Events

## Overview

Fix CaseID inconsistency between Goal_Setting events (logged by orchestration.py) and Student_Message/Bot_Response events (logged by mongodb_logger.py) to enable unified querying in `plan_vs_reality.py`.

## Requirements

### R1: Use group_id for All Events
The system MUST use `group_id` (not `chat_space_id`) in CaseID for all SRL-related events to enable unified querying.

### R2: CaseID Format
CaseID MUST follow format: `"{group_id}_session_{session_id}"` where:
- `group_id`: UUID of the group (e.g., "group123")
- `session_id`: Session number or timestamp (e.g., "1", "20260120100000")

### R3: Update orchestration.py
The Goal_Setting event logging in `orchestration.py` MUST use `group_id` instead of `chat_space_id`.

### R4: Update plan_vs_reality.py Query
The `analyze_session()` function MUST query events using `group_id`-based CaseID.

### R5: Backward Compatibility
The query function SHOULD support both old (chat_space_id) and new (group_id) CaseIDs during transition period.

### R6: Pass group_id to Functions
Functions that need group_id MUST receive it as a parameter:
- `orchestration.handle_message()` must pass group_id to goal validation
- `plan_vs_reality.analyze_session()` must accept group_id parameter

## Implementation

### Change 1: Update orchestration.py Goal_Setting Event

**File**: `app/services/orchestration.py`  
**Function**: `handle_message()` around line 430-463

#### Before
```python
# Goal_Setting event (line 451-462)
await self.mongo_logger.log_activity({
    "CaseID": f"{chat_space_id}_session_{session_id}",  # WRONG!
    "Activity": "Goal_Setting",
    ...
})
```

#### After
```python
# Goal_Setting event
await self.mongo_logger.log_activity({
    "CaseID": f"{group_id}_session_{session_id}",  # Use group_id
    "Activity": "Goal_Setting",
    ...
})
```

**Note**: `group_id` should already be available in the function context. If not, extract it from the message or chat_space lookup.

### Change 2: Update plan_vs_reality.analyze_session() Signature

**File**: `app/services/plan_vs_reality.py`  
**Function**: `analyze_session()` (line 86-150)

#### Before
```python
async def analyze_session(self, chat_space_id: str, session_id: str = "1"):
    case_id = f"{chat_space_id}_session_{session_id}"
    events = await self.mongo_logger.get_activity_logs(case_id=case_id)
    # ...
```

#### After
```python
async def analyze_session(self, group_id: str, session_id: str = "1", chat_space_id: str = None):
    """
    Analyze plan vs reality for a session.
    
    Args:
        group_id: Group UUID (required)
        session_id: Session number or timestamp (default: "1")
        chat_space_id: Optional chat_space_id for backward compatibility
    
    Returns:
        Analysis result dict
    """
    # Primary query with group_id
    case_id = f"{group_id}_session_{session_id}"
    events = await self.mongo_logger.get_activity_logs(case_id=case_id)
    
    # Backward compatibility: try chat_space_id if no events found
    if not events and chat_space_id:
        case_id = f"{chat_space_id}_session_{session_id}"
        events = await self.mongo_logger.get_activity_logs(case_id=case_id)
        logger.info(f"Using backward compat CaseID: {case_id}")
    
    if not events:
        return {...}  # Empty result
    
    # Rest of function...
```

### Change 3: Update Callers

Find all places that call `analyze_session()` and update to pass `group_id`:

```python
# Before
result = await analyzer.analyze_session(chat_space_id, session_id)

# After
result = await analyzer.analyze_session(group_id, session_id, chat_space_id)
```

## Test Cases

### TC1: Query Events with group_id
**Setup**: Log Goal_Setting and Student_Message events with same group_id  
**Action**: Call `analyze_session(group_id="group123", session_id="1")`  
**Expected**: Returns both plan and reality events.

### TC2: Backward Compatibility with chat_space_id
**Setup**: Log events with old chat_space_id format  
**Action**: Call `analyze_session(group_id="new_id", session_id="1", chat_space_id="old_id")`  
**Expected**: Falls back to chat_space_id query, returns events.

### TC3: No Events Found
**Setup**: No events logged  
**Action**: Call `analyze_session(group_id="nonexistent", session_id="1")`  
**Expected**: Returns empty result, no crash.

### TC4: Mixed Events (Transition Period)
**Setup**: Some events with group_id, some with chat_space_id  
**Action**: Call with both parameters  
**Expected**: Returns events from group_id query (primary).

## Dependencies

- `orchestration.py`: Must have access to group_id in handle_message()
- `mongodb_logger.py`: No changes needed (already uses correct CaseID)
- All callers of `analyze_session()`: Must be updated to pass group_id

## Acceptance Criteria

- [ ] Goal_Setting events logged with `group_id`-based CaseID
- [ ] `analyze_session()` accepts `group_id` parameter
- [ ] `analyze_session()` queries using `group_id`-based CaseID
- [ ] Backward compatibility with `chat_space_id` supported
- [ ] All callers updated to pass `group_id`
- [ ] Test cases pass
- [ ] Live verification shows both plan and reality events in single query

## Migration Strategy

**No data migration** - old events remain with chat_space_id CaseIDs, new events use group_id.

**Query strategy**:
1. Try group_id first (new format)
2. Fall back to chat_space_id if no results (old format)
3. Log which format was used for monitoring

## Rollout Plan

1. Deploy orchestration.py change (new events use group_id)
2. Deploy plan_vs_reality.py change (query supports both)
3. Monitor logs for backward compatibility usage
4. After 30 days, consider removing backward compat (optional)

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Callers don't have group_id | Medium | High | Audit all callers, add group_id lookup if needed |
| Backward compat adds complexity | Low | Low | Simple fallback, easy to remove later |
| Mixed events during transition | High | Low | Expected, backward compat handles it |

## Notes

- `chat_space_id` and `group_id` are different UUIDs
- `chat_space` is the discussion room, `group` is the student team
- Using `group_id` is more semantic for SRL analysis (team-based learning)
- Backward compatibility window: 30 days (configurable)
