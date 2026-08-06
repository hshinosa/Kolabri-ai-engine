## Why

Today, when `Guardrails.BLOCK` fires, the AI engine collapses the result into either a normal 200 response with a polite refusal text in the body, or into the generic 500 path. Neither is structurally distinguishable from a successful answer or a generic failure. Slice H3 in `harden-ai-engine-safety-and-observability` § H specifies a `outcome ∈ {"guarded","degraded","terminal"}` taxonomy. This change ships the first half of that taxonomy: `guarded`.

## What Changes

- Add `outcome` field to the JSON body of `global_exception_handler`, `http_exception_handler`, `validation_exception_handler` in `main.py`. Default value is `"terminal"` for the global handler, omitted for handlers that do not represent a terminal failure.
- Introduce `app/api/guarded_response.py` with a helper `guarded_response(rule_id: str, surface: str) -> JSONResponse` that produces the canonical guarded shape.
- Update Guardrails-aware call sites (chat-like routes) to return `guarded_response(...)` instead of a polite 200.
- Existing `detail` / `message` / `request_id` fields preserved.

## Capabilities

### Modified Capabilities

- `ai-engine-runtime-safety` — adds the requirement that guarded outcomes are surfaced as a structurally distinct response shape with `outcome="guarded"`.

## Impact

- `app/api/guarded_response.py` — new helper module.
- `main.py` — exception handlers add `outcome` to the body.
- `app/api/routes/chat.py` (or `app/api/routes.py` if S3 has not shipped yet) — call sites that consume Guardrails update their response shape.
- `tests/test_unit/test_guarded_response.py` — new tests.
- `tests/security/test_prompt_injection.py` — extend assertions to check `outcome="guarded"`.
