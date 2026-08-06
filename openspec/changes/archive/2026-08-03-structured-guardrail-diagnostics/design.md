## Context

`add-request-id-correlation` already binds `request_id` via `structlog.contextvars`, so any log line emitted during the request automatically carries it. This change is therefore mostly about emitting the right log line at the right place — the correlation field comes for free.

`GuardrailResult` already exposes `action`, `confidence`, `triggered_rules`, and `reason` as documented attributes (`app/core/guardrails.py:34-46`). No model change is required.

## Goals / Non-Goals

**Goals:**
- Every `BLOCK` and `SANITIZE` decision produces a single structured log line.
- The log line is searchable by `event=guardrail_decision`.
- Sensitive raw rule text does not appear in the log line.
- The same shape is emitted at input and output guardrails.

**Non-Goals:**
- Persisting guardrail decisions to Mongo.
- Introducing a new metrics counter (out of scope; that is part of H4 / future telemetry work).
- Changing `GuardrailResult` itself.

## Decisions

### D1: One log line per material decision
Material = decision changes the response shape (BLOCK, SANITIZE, REDIRECT). ALLOW with no triggered rules is silent. ALLOW with triggered rules but WARN-level confidence is logged at `info`.

### D2: Standard event name
Use `event=guardrail_decision` (structlog stdlib convention is positional first arg of the logger call). All search/alerting hooks key off this.

### D3: Field naming follows existing log style
- `action` = the `GuardrailAction.value` (`"block"`, `"sanitize"`, …).
- `rule_id` = the first triggered rule id (or empty string).
- `triggered_rules` = the full list of rule ids (no raw rule text).
- `surface` = `"input"` or `"output"`.
- `route` = the FastAPI route name.

## Risks / Trade-offs

- **Risk: log volume spike under attack** — many invalid requests could each emit a log line. Mitigation: log volume is acceptable given attack-investigation value; sampling is left for later.
- **Risk: route name not always available** — Mitigation: caller passes `route` explicitly; fallback `"unknown"` if not known.

## Open Questions

- None.
