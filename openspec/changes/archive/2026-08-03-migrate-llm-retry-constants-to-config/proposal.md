## Why

`app/services/llm.py:20-25` carries module-level constants `RETRY_DELAY_BASE = 1.0`, `RETRY_DELAY_MULTIPLIER = 2.0`, `TIMEOUT_CONNECT = 10.0`, `TIMEOUT_READ = 90.0`, and `MAX_RETRIES`. These are operationally sensitive — they directly control how the AI engine behaves under provider degradation — yet today they cannot be tuned without a code edit. The `improve-ai-engine-testability-and-maintainability` change identified this as slice S2 (§ G).

## What Changes

- Add new settings to `app/core/config.py`: `LLM_RETRY_DELAY_BASE`, `LLM_RETRY_DELAY_MULTIPLIER`, `LLM_TIMEOUT_CONNECT_SECONDS`, `LLM_TIMEOUT_READ_SECONDS`, `LLM_MAX_RETRIES`.
- Update `LLMService` (or equivalent caller in `llm.py`) to read each value from `settings.*`.
- Preserve the existing testing-mode override (`settings.ENV == "testing"` shrinks delays); keep it as-is, just sourcing the production values from settings.
- Remove the module-level constants in `llm.py`.

## Capabilities

### Modified Capabilities

- `ai-engine-service-maintainability` — adds the requirement that LLM retry/timeout/max-retries values live in `config.py`.

## Impact

- `app/core/config.py` — new settings.
- `app/services/llm.py` — read from settings, remove module-level constants.
- Circuit-breaker tests under `tests/test_unit/test_circuit_breaker.py` and any LLM unit tests confirm behavior is unchanged with default settings.
