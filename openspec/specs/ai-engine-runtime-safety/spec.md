# ai-engine-runtime-safety Specification

## Purpose
TBD - created by archiving change map-circuit-breaker-to-degraded-outcome. Update Purpose after archive.
## Requirements
### Requirement: Circuit-breaker open state surfaces as degraded outcome

The AI engine MUST translate an `OPEN` LLM circuit breaker into a 503 response with `outcome: "degraded"` instead of a generic 500.

#### Scenario: Breaker open during chat

- **WHEN** the LLM circuit breaker is `OPEN` and a chat-like request executes
- **THEN** the response status MUST be 503 and the body MUST include `outcome: "degraded"`, `reason: "llm_circuit_open"`, `message`, `retry_after`, and `request_id`

### Requirement: Provider retry exhaustion surfaces as degraded outcome

The AI engine MUST translate exhausted LLM retries into a 503 response with `outcome: "degraded"` rather than a generic 500.

#### Scenario: All LLM retries exhausted

- **WHEN** every retry attempt against the LLM provider fails
- **THEN** the response status MUST be 503 and the body MUST include `outcome: "degraded"`, `reason: "llm_retry_exhausted"`, `retry_after`, and `request_id`

### Requirement: Retry-after is set from circuit breaker recovery timeout

The AI engine MUST populate `retry_after` from the circuit breaker's remaining recovery time when the breaker is open, and from a sensible default otherwise.

#### Scenario: Retry-after from breaker

- **WHEN** the breaker is `OPEN` and the response is being constructed
- **THEN** `retry_after` MUST equal `max(1, breaker.recovery_timeout - elapsed_open_time)` in seconds

#### Scenario: Retry-after default when breaker not open

- **WHEN** the breaker is not `OPEN` but retries are exhausted
- **THEN** `retry_after` MUST equal a configured default (e.g. `LLM_RETRY_DEFAULT_RETRY_AFTER_SECONDS`)

