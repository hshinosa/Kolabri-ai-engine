# Fix Intervention Route Method And Schema Mismatch

## Problem Statement

After commit `c0550b1` (`split-routes-by-capability`) split the monolithic `routes.py` into per-capability modules, the new [app/api/routes/interventions.py](file:///Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/app/api/routes/interventions.py) introduced two regressions in the `/intervention/analyze` endpoint:

1. **Wrong service method name** — the route calls `intervention_service.analyze_conversation(messages, group_id, topic)`, but the service method is [analyze_and_intervene](file:///Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/app/services/intervention.py#L73-L79) (signature: `messages, topic, chat_room_id, last_intervention_time=None`). The current call would `AttributeError` at runtime against any real service instance.

2. **Schema mismatch** — the route returns `InterventionResponse(success=..., needs_intervention=..., intervention_type=..., message=..., confidence=..., error=...)` but the schema [InterventionResponse](file:///Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/app/api/schemas.py#L159-L167) requires `success, should_intervene, message, intervention_type, confidence, reason, error?`. Field name `needs_intervention` is unknown to the schema, and `reason` is required-but-missing. Pydantic rejects every response with 5 missing-field validation errors → endpoint returns 500.

These two bugs were masked because the 82 broken `@patch` targets in `test_routes_integration.py` (already addressed in `restore-routes-test-patches-after-split`) collected as `AttributeError` before the route ever ran.

## Proposed Solution

Update [app/api/routes/interventions.py](file:///Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/app/api/routes/interventions.py) to:

1. Call `intervention_service.analyze_and_intervene(messages, topic, chat_room_id)`.
2. Return `InterventionResponse` populated from the result with fields matching the schema:
   - `success=result.success`
   - `should_intervene=result.should_intervene`
   - `message=result.message or ""`
   - `intervention_type=result.intervention_type.value if result.intervention_type else ""`
   - `confidence=result.confidence or 0.0`
   - `reason=result.reason or ""`
   - `error=result.error`
3. On exception, return a sanitized `InterventionResponse(success=False, should_intervene=False, message="", intervention_type="", confidence=0.0, reason="Internal error", error="Internal error")`.

This restores the contract documented by the schema and the service.

## Why Now

`test_analyze_intervention_success` and `test_analyze_intervention_failure` are the last two tests blocking 0 failures in `test_routes_integration.py` after `restore-routes-test-patches-after-split`. Both tests already mock `analyze_and_intervene` (the correct method), so the test contract is fine — only the route was wrong.

## Scope

- [app/api/routes/interventions.py](file:///Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/app/api/routes/interventions.py) — fix the `/intervention/analyze` handler
- [tests/test_unit/test_routes_integration.py](file:///Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/tests/test_unit/test_routes_integration.py) — adjust assertions to match the corrected response shape

## Out of Scope

- The `/intervention/summary` and `/intervention/prompt` endpoints (already passing)
- Refactoring `analyze_and_intervene` itself
- Changing `InterventionResponse` schema
