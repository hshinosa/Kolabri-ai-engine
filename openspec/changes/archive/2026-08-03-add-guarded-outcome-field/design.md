## Context

The exception handlers in `main.py:170-220` currently emit a generic 500/4xx shape. `Guardrails.check_input` / `check_output` (`app/core/guardrails.py:233`, `:464`) already return a `GuardrailResult(action ∈ {ALLOW, BLOCK, WARN, REDIRECT, SANITIZE})` with `triggered_rules`. Today the call site decides what to send the user; a `BLOCK` typically becomes a normal-looking 200 chat response instead of a structurally distinct outcome.

`add-request-id-correlation` already injected `request_id` into every error body; this change extends that pattern to add `outcome` so a single integrator-friendly field can be branched on.

## Goals / Non-Goals

**Goals:**
- The `outcome` field is set on every error body produced by the global exception handlers.
- `Guardrails.BLOCK` decisions in chat-like routes set `outcome = "guarded"` and use HTTP 200 (chat surfaces) or 403 (non-chat surfaces).
- Existing `detail` and `message` fields are preserved.
- Backward compatibility: clients that ignore `outcome` continue to work.

**Non-Goals:**
- Mapping `degraded` and `terminal` outcomes (covered by H4 and the existing 500 path).
- Renaming the legacy `detail` / `message` fields.
- Touching the rate-limit response (`_rate_limit_exceeded_handler`).

## Decisions

### D1: `outcome` is a string enum at the wire level
Defined values: `"guarded"`, `"degraded"`, `"terminal"`. Extra values are rejected. The string form is more debuggable than a numeric code.

### D2: Guarded HTTP status depends on the surface
- Chat-like routes (`/api/chat`, `/api/ask`): 200 with `outcome="guarded"` to match conversational UX.
- Non-chat routes (e.g. `/api/documents/upload` rejecting unsafe content): 403 with `outcome="guarded"`.

### D3: Reason is taken from `triggered_rules`
The first triggered rule id is the `reason`. The full list goes to logs only; not sent to the user.

### D4: Sanitized message
The user-facing `message` for guarded outcomes is taken from a small static map keyed by rule id. No raw rule text is sent.

## Risks / Trade-offs

- **Risk: changing 200 with no outcome → 200 with outcome="guarded"** could surprise callers that interpreted 200 as "all clear". Mitigation: announce in proposal; existing fields stay so anything reading `detail` keeps working.
- **Risk: fragmented call sites** — Guardrails are called in multiple places. Mitigation: introduce a small helper `guarded_response(rule_id, surface)` that produces the response shape, used at every call site.

## Open Questions

- None.
