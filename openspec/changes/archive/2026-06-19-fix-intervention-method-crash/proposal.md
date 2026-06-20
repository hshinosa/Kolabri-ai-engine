# Fix Orchestration Intervention Method Crash

## Status
proposed

## Problem
`orchestration.py:585` calls `self.intervention.generate_intervention()` but this method does NOT exist in `ChatInterventionService` (`intervention.py`). The only public method is `analyze_and_intervene()`.

When intervention triggers (quality score below threshold), the entire orchestration pipeline crashes with `AttributeError`. The `except Exception` at `:260` catches it silently, returning a generic error message. The intervention system is completely DEAD in production.

## Evidence
```python
# orchestration.py:582-597
def _generate_intervention_message(self, analytics, quality_score, reason, topic):
    return self.intervention.generate_intervention(  # ← AttributeError!
        EngagementAnalysis(...),
        reason,
        topic,
    ).message
```

`ChatInterventionService` has:
- `analyze_and_intervene(messages, topic, chat_room_id, last_intervention_time)` → `InterventionResult`
- `generate_summary(messages, chat_room_id)` → `InterventionResult`

No `generate_intervention()` method exists.

## Proposed Fix

Rewrite `_generate_intervention_message` to use `analyze_and_intervene()`:

1. Change method from sync `def` to `async def` (since `analyze_and_intervene` is async)
2. Build messages list from `self._group_messages[group_id]` in the expected format
3. Call `await self.intervention.analyze_and_intervene(messages, topic, chat_room_id)`
4. Return `result.message` if `result.should_intervene`, else `None`
5. Update caller at `:205` to `await` the method

### Caller Update

```python
# Before (orchestration.py:205):
int_msg = self._generate_intervention_message(analytics, q_score, reason, topic)

# After:
int_msg = await self._generate_intervention_message(
    group_id, analytics, q_score, reason, topic, kwargs
)
```

### Method Rewrite

```python
async def _generate_intervention_message(
    self, group_id, analytics, quality_score, reason, topic, kwargs
) -> Optional[str]:
    """Generate intervention message via ChatInterventionService."""
    async with self._state_lock:
        raw_msgs = self._group_messages.get(group_id, [])

    messages = [
        {
            "role": "user",
            "content": m["message"],
            "sender_id": m["user_id"],
        }
        for m in raw_msgs[-10:]
    ]

    chat_room_id = kwargs.get("chat_room_id") or group_id

    try:
        async with self._state_lock:
            last_time = self._last_intervention.get(group_id)

        result = await self.intervention.analyze_and_intervene(
            messages=messages,
            topic=topic or "General",
            chat_room_id=chat_room_id,
            last_intervention_time=last_time,
        )

        if result.should_intervene and result.message:
            return result.message
    except Exception:
        logger.exception("intervention_generation_failed", group_id=group_id)

    return None
```

## Files Changed
- `app/services/orchestration.py` — rewrite `_generate_intervention_message` (lines 582-597), update caller (line 205)

## Testing
- Unit test: mock `ChatInterventionService.analyze_and_intervene`, verify orchestration calls it correctly
- Integration test: trigger intervention (low quality score), verify no AttributeError, verify intervention message generated
- Verify existing test suite still passes

## Risk
- **Low**: Pure bug fix, no new features
- Caller is already inside `if needed:` block, so intervention only triggers when quality warrants it
