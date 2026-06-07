## 1. Pre-flight

- [x] 1.1 Confirm 2 failing tests: `pytest tests/test_unit/test_routes_integration.py::test_analyze_intervention_success tests/test_unit/test_routes_integration.py::test_analyze_intervention_failure --no-cov`
- [x] 1.2 Verify `analyze_and_intervene` signature in `app/services/intervention.py`
- [x] 1.3 Verify `InterventionResponse` field set in `app/api/schemas.py`

## 2. Route fix

- [x] 2.1 Replace `intervention_service.analyze_conversation(...)` call with `intervention_service.analyze_and_intervene(messages=..., topic=..., chat_room_id=request.chat_room_id)`
- [x] 2.2 Replace return-on-success construction with schema-compliant fields (`should_intervene`, `message`, `intervention_type`, `confidence`, `reason`, `error`)
- [x] 2.3 Replace return-on-error construction with schema-compliant sanitized body (`success=False, should_intervene=False, message="", intervention_type="", confidence=0.0, reason="Internal error", error="Internal error"`)
- [x] 2.4 Run `lsp_diagnostics` on `app/api/routes/interventions.py` — clean

## 3. Test fix

- [x] 3.1 Update `test_analyze_intervention_failure` assertion for `data['error']` to `'Internal error'`
- [x] 3.2 Confirm `test_analyze_intervention_success` passes unchanged

## 4. Verify

- [x] 4.1 `pytest tests/test_unit/test_routes_integration.py::test_analyze_intervention_success tests/test_unit/test_routes_integration.py::test_analyze_intervention_failure --no-cov` — both pass
- [x] 4.2 `pytest tests/test_unit/test_routes_integration.py --no-cov -q` — 0 failed
- [x] 4.3 Full suite: `pytest tests/ --ignore=tests/benchmarks --ignore=benchmarks --no-cov -q --no-header` — no new failures vs baseline (0 from prior 41)
- [x] 4.4 `openspec validate fix-intervention-route-method-and-schema-mismatch --strict`
