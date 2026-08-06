## Context

`llm.py:20-25` and `llm.py:61-72` use module-level constants for retry/timeout. The values flow into `httpx.Timeout` and `tenacity` retry configuration. There is already a special case for `settings.ENV == "testing"` at line 116-117 that shrinks delays — that special case stays, only the production values are migrated.

## Goals / Non-Goals

**Goals:**
- All retry/timeout/max-retries values come from `settings`.
- Default values match today's production behavior.
- Testing-mode shortening at `llm.py:116-117` continues to work without modification.

**Non-Goals:**
- Tuning any value.
- Changing retry strategy (still tenacity-based exponential backoff).
- Touching circuit breaker thresholds (covered by `CIRCUIT_BREAKER_RECOVERY_TIMEOUT` already in settings).

## Decisions

### D1: One setting per knob, not a single dict
Each knob has its own `LLM_*` setting so operators can override individually via env var. A nested dict would force one big env var.

### D2: Keep test mode logic untouched
`llm.py:116-117` already pivots on `settings.ENV == "testing"`. That logic remains; only the production constants on the other branch are migrated.

### D3: Naming
- `LLM_RETRY_DELAY_BASE` (was `RETRY_DELAY_BASE`)
- `LLM_RETRY_DELAY_MULTIPLIER` (was `RETRY_DELAY_MULTIPLIER`)
- `LLM_TIMEOUT_CONNECT_SECONDS` (was `TIMEOUT_CONNECT`)
- `LLM_TIMEOUT_READ_SECONDS` (was `TIMEOUT_READ`)
- `LLM_MAX_RETRIES` (was `MAX_RETRIES`)

`*_SECONDS` suffix on timeouts makes the unit unambiguous.

## Risks / Trade-offs

- **Risk: any test or other module imports the constants directly** → Mitigation: search before removal; if found, update those imports to read from `settings`.
- **Risk: env var collision** → Mitigation: `LLM_` prefix is not used by any other setting today.

## Open Questions

- None.
