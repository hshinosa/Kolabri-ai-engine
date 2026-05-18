## ADDED Requirements

### Requirement: LLM retry, timeout, and max-retries values live in configuration

The AI engine MUST source LLM retry delay base, retry delay multiplier, connect timeout, read timeout, and max retries from `app/core/config.py`, not from module-level constants in `llm.py`.

#### Scenario: LLM client uses configured timeouts

- **WHEN** the LLM service constructs its HTTP client
- **THEN** the connect and read timeouts MUST come from `settings.LLM_TIMEOUT_CONNECT_SECONDS` and `settings.LLM_TIMEOUT_READ_SECONDS`

#### Scenario: LLM retries respect configured backoff

- **WHEN** the LLM service builds its tenacity retry wait policy
- **THEN** the wait base and multiplier MUST come from `settings.LLM_RETRY_DELAY_BASE` and `settings.LLM_RETRY_DELAY_MULTIPLIER`, except when `settings.ENV == "testing"` where the existing 0.01s shortcut is preserved

#### Scenario: LLM retry budget is configurable

- **WHEN** the LLM service is asked how many retries to attempt
- **THEN** the value MUST come from `settings.LLM_MAX_RETRIES`
