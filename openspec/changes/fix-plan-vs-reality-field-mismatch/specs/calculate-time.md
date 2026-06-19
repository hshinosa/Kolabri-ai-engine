# Spec: Fix `_calculate_time_allocation()` Function

## Overview

Fix `_calculate_time_allocation()` to handle NoneType errors and calculate time allocation from event timestamps instead of non-existent `goal.deadline` and `goal.created_at` fields.

## Requirements

### R1: Use Event Timestamps
The function MUST calculate time allocation from event `Timestamp` fields, not from goal object attributes.

### R2: Handle Missing Timestamps
The function MUST gracefully handle cases where:
- No timestamps available
- Only one timestamp available
- Timestamps are strings (ISO format)
- Timestamps are datetime objects

### R3: Fallback Strategy
The function MUST provide reasonable fallback values:
- If insufficient timestamps: assume 30 minutes per goal/message
- If parsing fails: use fallback, don't crash

### R4: Time Format Handling
The function MUST handle:
- ISO 8601 format: `"2026-01-20T10:00:00Z"`
- ISO 8601 with timezone: `"2026-01-20T10:00:00+00:00"`
- Datetime objects (if already parsed)

### R5: Separate Calculations
The function SHOULD provide separate time calculations for:
- Plan (goals): time allocated per goal
- Reality (messages): time spent in discussion

## Implementation

**File**: `app/services/plan_vs_reality.py`  
**Function**: `_calculate_time_allocation()` (lines 520+)

### Before
```python
def _calculate_time_allocation(self, goal_events):
    # Tries to access goal.deadline and goal.created_at
    # These fields don't exist in event structure
    # Causes: TypeError: unsupported operand type(s) for -: 'NoneType' and 'NoneType'
    duration = goal.deadline - goal.created_at  # CRASH!
    return {...}
```

### After
```python
def _calculate_time_allocation(self, events, default_minutes_per_item=30):
    """
    Calculate time allocation from event timestamps.
    
    Args:
        events: List of event dictionaries with Timestamp fields
        default_minutes_per_item: Fallback minutes per event if timestamps unavailable
    
    Returns:
        Dict with time allocation data
    """
    if not events:
        return {
            "total_minutes": 0,
            "duration_minutes": 0,
            "per_item": []
        }
    
    # Extract timestamps
    timestamps = []
    for event in events:
        ts = event.get("Timestamp") or event.get("timestamp")
        if ts:
            timestamps.append(ts)
    
    # If insufficient timestamps, use fallback
    if len(timestamps) < 2:
        total_minutes = len(events) * default_minutes_per_item
        return {
            "total_minutes": total_minutes,
            "duration_minutes": total_minutes,
            "per_item": [
                {"minutes": default_minutes_per_item, "timestamp": ts if ts else None}
                for ts in timestamps
            ]
        }
    
    # Parse timestamps
    parsed_timestamps = []
    for ts in timestamps:
        try:
            if isinstance(ts, str):
                # Handle ISO format with or without timezone
                if ts.endswith('Z'):
                    ts = ts.replace('Z', '+00:00')
                parsed = datetime.fromisoformat(ts)
            elif isinstance(ts, datetime):
                parsed = ts
            else:
                continue
            parsed_timestamps.append(parsed)
        except (ValueError, AttributeError) as e:
            logger.debug(f"Failed to parse timestamp: {ts}, error: {e}")
            continue
    
    # If parsing failed, use fallback
    if len(parsed_timestamps) < 2:
        total_minutes = len(events) * default_minutes_per_item
        return {
            "total_minutes": total_minutes,
            "duration_minutes": total_minutes,
            "per_item": [
                {"minutes": default_minutes_per_item, "timestamp": ts}
                for ts in timestamps
            ]
        }
    
    # Calculate duration
    try:
        min_ts = min(parsed_timestamps)
        max_ts = max(parsed_timestamps)
        duration = max_ts - min_ts
        total_minutes = duration.total_seconds() / 60
        
        # Calculate per-item allocation
        per_item = []
        for i, ts in enumerate(timestamps):
            item_minutes = total_minutes / len(events) if i < len(events) else 0
            per_item.append({
                "minutes": round(item_minutes, 2),
                "timestamp": ts
            })
        
        return {
            "total_minutes": round(total_minutes, 2),
            "duration_minutes": round(total_minutes, 2),
            "per_item": per_item,
            "start_time": min_ts.isoformat(),
            "end_time": max_ts.isoformat()
        }
    except Exception as e:
        logger.error(f"Time calculation failed: {e}")
        total_minutes = len(events) * default_minutes_per_item
        return {
            "total_minutes": total_minutes,
            "duration_minutes": total_minutes,
            "per_item": []
        }
```

## Test Cases

### TC1: Calculate Time from Multiple Events
**Input**:
```python
events = [
    {"Timestamp": "2026-01-20T10:00:00Z"},
    {"Timestamp": "2026-01-20T10:15:00Z"},
    {"Timestamp": "2026-01-20T10:30:00Z"}
]
```

**Expected Output**:
```python
{
    "total_minutes": 30.0,
    "duration_minutes": 30.0,
    "per_item": [
        {"minutes": 10.0, "timestamp": "2026-01-20T10:00:00Z"},
        {"minutes": 10.0, "timestamp": "2026-01-20T10:15:00Z"},
        {"minutes": 10.0, "timestamp": "2026-01-20T10:30:00Z"}
    ],
    "start_time": "2026-01-20T10:00:00+00:00",
    "end_time": "2026-01-20T10:30:00+00:00"
}
```

### TC2: Fallback with Single Event
**Input**: `events = [{"Timestamp": "2026-01-20T10:00:00Z"}]`  
**Expected**: `{"total_minutes": 30, "duration_minutes": 30, "per_item": [...]}`

### TC3: Fallback with No Timestamps
**Input**: `events = [{"content": "no timestamp"}]`  
**Expected**: `{"total_minutes": 30, "duration_minutes": 30, "per_item": []}`

### TC4: Empty Events
**Input**: `events = []`  
**Expected**: `{"total_minutes": 0, "duration_minutes": 0, "per_item": []}`

### TC5: Invalid Timestamp Format
**Input**: `events = [{"Timestamp": "invalid-date"}]`  
**Expected**: Fallback to 30 minutes, no crash.

### TC6: Datetime Objects
**Input**:
```python
from datetime import datetime
events = [
    {"Timestamp": datetime(2026, 1, 20, 10, 0, 0)},
    {"Timestamp": datetime(2026, 1, 20, 10, 30, 0)}
]
```

**Expected**: `{"total_minutes": 30.0, ...}`

### TC7: Mixed String and Datetime
**Input**: Mix of string and datetime timestamps  
**Expected**: Should parse both, calculate duration.

## Dependencies

- `datetime` module (standard library)
- `logger` from `app.core.logging`

## Acceptance Criteria

- [ ] Function calculates time from event `Timestamp` fields
- [ ] Function handles ISO 8601 format strings
- [ ] Function handles datetime objects
- [ ] Function handles missing timestamps gracefully
- [ ] Function handles invalid timestamp formats gracefully
- [ ] Function provides fallback values (30 min per item)
- [ ] Function returns start_time and end_time when available
- [ ] Function returns per-item time allocation
- [ ] All test cases pass
- [ ] No TypeError crashes

## Notes

- The old code tried to access `goal.deadline` and `goal.created_at` which don't exist
- Event timestamps are in ISO 8601 format: `"2026-01-20T10:00:00Z"`
- The `Z` suffix indicates UTC timezone
- Python's `datetime.fromisoformat()` requires `+00:00` instead of `Z` for timezone
- Fallback of 30 minutes per item is reasonable for discussion sessions
