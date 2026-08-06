## Why

`Guardrails.check_input` (`app/core/guardrails.py:233`) and `check_output` (`:464`) already return a `GuardrailResult` with an `action`, `confidence`, and `triggered_rules`. Today this information is consumed by the call site to shape the response, but it is not consistently emitted to logs in a structured form. Operators reviewing a guarded response have no machine-readable record of which rule fired with what confidence. Slice H5 in `harden-ai-engine-safety-and-observability` § H requires structured diagnostics for guardrail decisions.

## What Changes

- Wrap every consumer of `GuardrailResult` to emit a structured `guardrail_decision` log line whenever `action != ALLOW` (and optionally when `ALLOW` has triggered rules with WARN-level confidence).
- The log line carries: `action`, `rule_id`, `confidence`, `triggered_rules`, `surface` (`"input" | "output"`), `route`, and the `request_id` (already bound by `add-request-id-correlation`).
- Introduce `app/core/guardrail_diagnostics.py` with a single helper `log_guardrail_decision(result: GuardrailResult, surface: str, route: str)` so call sites do not duplicate the logging shape.

## Capabilities

### Modified Capabilities

- `ai-engine-observability` — adds the requirement that guardrail decisions emit a structured diagnostic record correlated to the request.

## Impact

- `app/core/guardrail_diagnostics.py` — new helper module.
- Call sites that consume `Guardrails.check_input` / `check_output` (e.g. `app/api/routes.py` chat handlers, or `app/api/routes/chat.py` after S3) — invoke the helper after each guardrail check.
- `tests/test_unit/test_guardrail_diagnostics.py` — new tests asserting log shape using `structlog.testing.capture_logs`.
- `tests/security/test_prompt_injection.py` — extend assertions to verify a `guardrail_decision` log line is emitted on `BLOCK`.
