# Design

## Method Signature Alignment

`ChatInterventionService.analyze_and_intervene`:
```python
async def analyze_and_intervene(
    self,
    messages: List[Dict[str, Any]],
    topic: str,
    chat_room_id: str,
    last_intervention_time: Optional[datetime] = None,
) -> InterventionResult:
```

`InterventionRequest` (already defined in `app/api/schemas.py`):
- `messages: List[ChatMessage]`
- `topic: str`
- `chat_room_id: str`
- (other fields ignored for analyze)

Map: pass `messages` (after dict-conversion), `request.topic`, `request.chat_room_id`. Optional `last_intervention_time` left unset (service default).

## Response Mapping

`InterventionResult` fields (dataclass / SimpleNamespace from service):
- `success: bool`
- `should_intervene: bool`
- `message: str`
- `intervention_type: InterventionType` (enum with `.value`) or None
- `confidence: float`
- `reason: str`
- `error: Optional[str]`

`InterventionResponse` fields (Pydantic):
- `success`, `should_intervene`, `message`, `intervention_type: str`, `confidence: float`, `reason: str`, `error: Optional[str]`

Mapping handles None on enum and on optional fields by coercing to schema-acceptable defaults (`""`, `0.0`).

## Error Path

The route already ran `logger.exception` and returned a sanitized `InterventionResponse`. The current code passes `needs_intervention=False, error="Internal error"` — which fails schema validation. The fix replaces that with the schema-compliant body and keeps `error="Internal error"` (matches the safe-by-construction contract from `sanitize-service-error-propagation-in-responses`).

## Test Adjustments

`test_analyze_intervention_success`: existing helper `make_intervention_result` returns SimpleNamespace with `should_intervene`, `message`, `intervention_type=SimpleNamespace(value="redirect")`, `confidence`, `reason`, `error`. Existing assertion is on `data['should_intervene']`. After the route fix this passes as-is.

`test_analyze_intervention_failure`: side_effect raises Exception. Before fix the `error="Internal error"` body failed schema validation (5 missing fields). After fix the sanitized body validates. The test currently asserts:
```python
assert response.status_code == 200
assert data['success'] is False
assert data['error'] == 'analysis failed'
```
Update assertion of `error` to `'Internal error'` (the safe-by-construction contract).

## Risk

- Production callers expecting `needs_intervention` in the JSON would break. Search for callers — none found in repo (only test). Frontend callers TBD; if any exist, they were broken before this fix because the endpoint always returned 500.
