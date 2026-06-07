# Intervention Routes

## ADDED Requirements

### Requirement: /intervention/analyze SHALL invoke the documented service method

The `/intervention/analyze` endpoint in `app/api/routes/interventions.py` SHALL call `ChatInterventionService.analyze_and_intervene(messages, topic, chat_room_id)`. It MUST NOT call `analyze_conversation` (which does not exist on the service).

#### Scenario: Successful analyze call

- Given a request with `messages`, `topic`, `chat_room_id`
- When the route handler executes
- Then it MUST call `intervention_service.analyze_and_intervene` with those arguments
- And it MUST NOT call `intervention_service.analyze_conversation`
- And the response status MUST be 200

### Requirement: InterventionResponse SHALL be schema-compliant

The `/intervention/analyze` endpoint SHALL return an `InterventionResponse` whose JSON body matches the Pydantic schema. The body MUST include all required fields: `success`, `should_intervene`, `message`, `intervention_type`, `confidence`, `reason`. The body MUST NOT use `needs_intervention` (which is not in the schema).

#### Scenario: Mocked happy-path response

- Given the service returns `InterventionResult(success=True, should_intervene=True, message="Mari fokus", intervention_type=<enum value="redirect">, confidence=0.88, reason="off-topic")`
- When the route returns the response
- Then `response.status_code` MUST be 200
- And `response.json()['should_intervene']` MUST be True
- And `response.json()['intervention_type']` MUST be `"redirect"`
- And `response.json()['message']` MUST be `"Mari fokus"`
- And `response.json()['confidence']` MUST equal 0.88
- And `response.json()['reason']` MUST be `"off-topic"`

#### Scenario: Service raises an exception

- Given the service `analyze_and_intervene` raises any exception
- When the route catches it
- Then `response.status_code` MUST be 200 (graceful degradation)
- And `response.json()['success']` MUST be False
- And `response.json()['should_intervene']` MUST be False
- And `response.json()['error']` MUST be `"Internal error"` (sanitized per safe-by-construction contract)
- And the response body MUST validate against the `InterventionResponse` Pydantic schema (all required fields present)
