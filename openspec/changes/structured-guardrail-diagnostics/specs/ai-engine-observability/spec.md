## ADDED Requirements

### Requirement: Guardrail decisions emit structured diagnostics

The AI engine MUST emit a single structured `guardrail_decision` log line for every Guardrails invocation that materially shapes the response.

#### Scenario: Block decision is logged

- **WHEN** `Guardrails.check_input` or `Guardrails.check_output` returns `BLOCK`
- **THEN** a structured log line `event=guardrail_decision` MUST be emitted with at minimum: `action="block"`, `rule_id`, `confidence`, `triggered_rules`, `surface`, and `request_id`

#### Scenario: Sanitize decision is logged

- **WHEN** `Guardrails.check_input` returns `SANITIZE`
- **THEN** a structured log line `event=guardrail_decision` MUST be emitted with `action="sanitize"`, `rule_id`, `confidence`, `triggered_rules`, `surface`, and `request_id`

#### Scenario: Allow decision is not over-logged

- **WHEN** `Guardrails.check_input` or `Guardrails.check_output` returns `ALLOW` and no rule was triggered
- **THEN** the system MAY skip the `guardrail_decision` log line to avoid log spam; if emitted, it MUST still carry the same field shape

### Requirement: Diagnostics carry request correlation

The AI engine MUST include `request_id` on every `guardrail_decision` log line so a guardrail decision can be tied back to the originating request.

#### Scenario: Log line is correlatable

- **WHEN** any `guardrail_decision` log line is emitted during request processing
- **THEN** it MUST include the `request_id` bound for the active request via `structlog.contextvars`
