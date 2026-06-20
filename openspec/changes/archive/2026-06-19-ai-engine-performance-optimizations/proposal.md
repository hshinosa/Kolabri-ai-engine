# AI Engine Performance Optimizations

## Status
proposed

## Summary
Four performance fixes for the AI Engine orchestration pipeline targeting latency reduction and resource efficiency.

## PERF-AI-02: Double Retry (tenacity x OpenAI SDK)

### Problem
`llm.py:111-116` — `AsyncOpenAI(max_retries=LLM_MAX_RETRIES=3)` AND `@retry(stop_after_attempt(3))` on `_execute_with_retry`. On transient errors, up to 9 total attempts.

### Fix
Set `max_retries=0` in `AsyncOpenAI()` constructor. Let tenacity handle all retry logic exclusively.

```python
# llm.py:111
self.client = AsyncOpenAI(
    api_key=api_key,
    base_url=base_url,
    http_client=self._http_client,
    max_retries=0,  # ← was: settings.LLM_MAX_RETRIES
)
```

### Risk
- **None**: tenacity already handles retries with proper backoff. SDK retry was redundant.

---

## PERF-AI-03: Retry on 4xx Errors

### Problem
`llm.py:200-201` — Decorator retries on ALL `APIError` (including 400/422 which are permanent failures). Wasted latency.

### Current State (Partially Mitigated)
The function body at `:233-236` already re-checks: only re-raises for 5xx, returns error for 4xx. So tenacity won't actually retry 4xx. But the decorator declaration is misleading and the check is fragile.

### Fix
Narrow the tenacity decorator to only retry transient errors:

```python
# llm.py:192-203
@retry(
    stop=stop_after_attempt(settings.LLM_MAX_RETRIES),
    wait=wait_exponential(...),
    retry=retry_if_exception_type((RateLimitError, APIConnectionError, APIError))
          & retry_if_exception_type(APIError)
          .with_predicate(lambda exc: getattr(exc, 'status_code', 0) >= 500),
    reraise=True,
)
```

Or simpler — just remove the `| retry_if_exception_type(APIError)` line since the function body already filters:

```python
@retry(
    stop=stop_after_attempt(settings.LLM_MAX_RETRIES),
    wait=wait_exponential(...),
    retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
    reraise=True,
)
```

Then remove the 5xx re-raise logic from `_execute_with_retry` body since tenacity now handles it via exception type matching.

### Risk
- **Low**: Need to ensure 5xx errors still propagate to tenacity. Test with mock server returning 500.

---

## PERF-AI-04: Sequential Mongo Writes

### Problem
`orchestration.py:141-185` — Two `await self.mongo_logger.log_activity(...)` calls (Student_Message + Bot_Response) are sequential.

### Fix
Wrap in `asyncio.gather()`:

```python
# orchestration.py:140-185
await asyncio.gather(
    self.mongo_logger.log_activity({
        "CaseID": case_id,
        "Activity": "Student_Message",
        # ... (existing fields)
    }),
    self.mongo_logger.log_activity({
        "CaseID": case_id,
        "Activity": "Bot_Response",
        # ... (existing fields)
    }),
)
```

### Risk
- **Very Low**: Both writes are independent (different Activity names, same CaseID). No ordering dependency.

---

## PERF-AI-09: Sequential `_track_message` Calls

### Problem
`orchestration.py:537-554` — `_track_message` acquires `_state_lock` and calls `logic_listener.track_participation` + `logic_listener.update_last_message_time` sequentially.

### Fix
```python
async def _track_message(self, group_id, user_id, message, analytics):
    """Track message with thread-safe state updates."""
    async with self._state_lock:
        # ... existing state updates ...

        # Parallelize independent logic_listener calls
        await asyncio.gather(
            self.logic_listener.track_participation(group_id, user_id),
            self.logic_listener.update_last_message_time(group_id),
        )
```

### Risk
- **Very Low**: Both calls operate on independent state (participation tracking vs timestamp tracking).

---

## Files Changed
- `app/services/llm.py` — PERF-AI-02 (max_retries=0), PERF-AI-03 (narrow retry types)
- `app/services/orchestration.py` — PERF-AI-04 (asyncio.gather logs), PERF-AI-09 (asyncio.gather track_message)

## Testing
- Unit tests: verify retry behavior with mock 4xx/5xx responses
- Integration: verify log_activity writes complete correctly with gather
- Performance: measure orchestration latency before/after

## Estimated Impact
- PERF-AI-02: Eliminates up to 6 wasted retry attempts on transient errors
- PERF-AI-03: Eliminates wasted retries on permanent 4xx failures (~1-2s saved)
- PERF-AI-04: ~50-100ms saved per message (parallel mongo writes)
- PERF-AI-09: ~20-50ms saved per message (parallel tracking)
