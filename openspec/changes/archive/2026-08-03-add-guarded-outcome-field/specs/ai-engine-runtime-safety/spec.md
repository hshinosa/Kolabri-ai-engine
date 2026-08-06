## ADDED Requirements

### Requirement: Guarded outcomes are structurally distinguishable

The AI engine MUST surface `Guardrails.BLOCK` decisions as a response shape carrying `outcome: "guarded"` so consumers can branch on the field rather than parsing the body text.

#### Scenario: Guardrails block on chat-like surface

- **WHEN** a request to a chat-like route triggers `Guardrails.BLOCK`
- **THEN** the response MUST be HTTP 200 with body containing `outcome: "guarded"`, `reason: <rule_id>`, `message: <safe_message>`, and `request_id`

#### Scenario: Guardrails block on non-chat surface

- **WHEN** a request to a non-chat route triggers `Guardrails.BLOCK`
- **THEN** the response MUST be HTTP 403 with body containing `outcome: "guarded"`, `reason: <rule_id>`, `message: <safe_message>`, and `request_id`

### Requirement: Terminal failures are tagged with outcome

The AI engine MUST tag responses produced by the global exception handler with `outcome: "terminal"` so they are distinguishable from guarded and degraded outcomes.

#### Scenario: Unhandled exception surfaces terminal outcome

- **WHEN** an unhandled exception is converted to a 500 response
- **THEN** the response body MUST include `outcome: "terminal"` while preserving the existing `detail`, `message`, and `request_id` fields

### Requirement: Guarded responses do not leak rule details

The AI engine MUST NOT include the full `triggered_rules` list or raw rule text in guarded response bodies; only the canonical `reason` (rule id) and a sanitized `message` from a static map.

#### Scenario: Triggered rules stay server-side

- **WHEN** a guarded response is constructed
- **THEN** the response body MUST omit `triggered_rules` and any raw rule text; only `reason` and `message` are surfaced
