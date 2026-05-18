## Context

`app/services/circuit_breaker.py:115` defines `async def call(self, func, *args, **kwargs)` which raises an exception when the breaker is open. `app/services/llm.py:72` configures `max_retries`. Today the call sites do not differentiate between "breaker open" (transient, retryable from upstream) and "retries exhausted" (provider truly down) — both bubble to the global handler.

The new `outcome="degraded"` taxonomy has already been introduced for guarded outcomes (slice H3). H4 wires the degraded variant.

## Goals / Non-Goals

**Goals:**
- A 503 response with `outcome="degraded"` is returned for breaker-open and retry-exhausted cases.
- `retry_after` field is populated from the breaker's `recovery_timeout` when applicable.
- Existing successful path is unchanged.

**Non-Goals:**
- Implementing distributed tracing.
- Adding new circuit breakers for non-LLM dependencies (covered by H2).
- Changing the breaker's algorithm.

## Decisions

### D1: Sentinel exception type
Introduce `LLMDegradedError(Exception)` carrying `reason` and `retry_after`. This is what the breaker-open branch and the post-retry branch raise. The global handler does not catch this — a dedicated handler does.

### D2: Dedicated exception handler beats generic catch
Adding a `@app.exception_handler(LLMDegradedError)` keeps the global handler as the truly-unknown-failure path. Easier to reason about than embedding logic in `global_exception_handler`.

### D3: `retry_after` from breaker
Read `breaker.metadata` exposed via `circuit_breaker.get_metrics()` to compute remaining recovery seconds. If breaker is closed but retries are exhausted, fall back to `settings.LLM_RETRY_DEFAULT_RETRY_AFTER_SECONDS` (default 30).

## Risks / Trade-offs

- **Risk: clients still treat 503 as 5xx and trigger their own retries** → Mitigation: emit `Retry-After` header in addition to body field; that is the standard signal.
- **Risk: third-party libs in the call stack swallow `LLMDegradedError`** → Mitigation: define the error early in `llm.py` and raise it directly from the public method, not from inside tenacity wait policy.

## Open Questions

- None.
