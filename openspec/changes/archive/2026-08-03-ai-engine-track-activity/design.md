## Context

Logic Listener's `update_last_message_time(group_id)` is defined at line 118 of `logic_listener.py`. It's an async method that acquires `_state_lock` and updates `_last_message_timestamp[group_id] = time.time()`. The endpoint needs to call this method on the singleton Logic Listener instance.

The endpoint must be lightweight: no LLM, no embedding, no MongoDB write. Just an in-memory dict update. Response time should be < 5ms.

Authentication: same pattern as other endpoints — `X-API-Key` header checked by existing auth middleware.

## Goals / Non-Goals

**Goals:**
- Update Logic Listener's `_last_message_timestamp` for the given group
- Return immediately after update — no async processing
- Protected by existing auth middleware

**Non-Goals:**
- Not tracking individual users — only group-level timestamp
- Not logging to MongoDB — this is a pure in-memory operation
- Not triggering any analysis or intervention — just timestamp update

## Decisions

**D1: Use existing auth middleware**
The endpoint is behind the same `X-API-Key` auth as all other endpoints. No special auth needed.

**D2: `TrackActivityRequest` schema: `group_id: str` only**
Minimal schema. Only `group_id` is needed to update the timestamp.

**D3: Synchronous response**
`update_last_message_time()` is async but fast (just dict update with lock). Await it and return `{"success": true}` immediately.

**D4: Place endpoint in routes.py near analytics section**
Logically related to analytics/monitoring. Add after the existing analytics endpoints.

## Risks / Trade-offs

- **[Risk] High call frequency** → Mitigation: endpoint is O(1), in-memory only. Can handle thousands of calls per second.
- **[Risk] Logic Listener singleton not initialized** → Mitigation: `get_logic_listener()` is a singleton factory — always returns initialized instance.

## Open Questions

- None. This is a straightforward endpoint.
