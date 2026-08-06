## Why

When the LLM circuit breaker is `OPEN` or all retries are exhausted, the AI engine raises an exception that bubbles up to `global_exception_handler`, producing a generic `500 INTERNAL_SERVER_ERROR`. That collapses three semantically different failures (transient provider unreachability, persistent provider failure, internal bug) into one shape. Slice H4 in `harden-ai-engine-safety-and-observability` § H specifies the `degraded` outcome for these cases.

## What Changes

- Define a sentinel exception `LLMDegradedError(reason: str, retry_after: int)` raised by `LLMService` when the breaker is open or retries are exhausted.
- Add a dedicated `@app.exception_handler(LLMDegradedError)` in `main.py` that returns 503 with body `{outcome: "degraded", reason, message, retry_after, request_id, detail: "DEGRADED"}`.
- Add `LLM_RETRY_DEFAULT_RETRY_AFTER_SECONDS` to `app/core/config.py` (default 30).
- Existing 500 path stays for non-LLM failures.

## Capabilities

### Modified Capabilities

- `ai-engine-runtime-safety` — adds the requirement that LLM circuit-breaker `OPEN` and retry exhaustion produce a structurally distinct degraded outcome with HTTP 503.

## Impact

- `app/services/llm.py` — raise `LLMDegradedError` from the breaker-open branch and the post-retry branch.
- `app/services/llm_errors.py` (or extension to `llm.py`) — define `LLMDegradedError`.
- `main.py` — add `LLMDegradedError` exception handler.
- `app/core/config.py` — add `LLM_RETRY_DEFAULT_RETRY_AFTER_SECONDS`.
- `tests/test_unit/test_circuit_breaker.py` — assert the breaker-open path produces `LLMDegradedError`.
- `tests/test_integration/test_api_routes.py` — assert HTTP 503 + `outcome="degraded"` when breaker is open.
