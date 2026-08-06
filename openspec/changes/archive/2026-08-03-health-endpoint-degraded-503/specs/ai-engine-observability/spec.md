## ADDED Requirements

### Requirement: Health endpoint surfaces degraded state as HTTP 503

The AI engine MUST return HTTP 503 from `/api/health` when any tracked dependency or circuit breaker is in a non-healthy state.

#### Scenario: All dependencies healthy

- **WHEN** every tracked dependency reports healthy
- **THEN** the response status MUST be 200 and the body MUST report `status: "healthy"`

#### Scenario: Any dependency degraded

- **WHEN** at least one tracked dependency reports degraded or down
- **THEN** the response status MUST be 503 and the body MUST report `status: "degraded"`

### Requirement: Health endpoint reports per-dependency breakdown

The AI engine MUST expose per-dependency status in the health response so operators can identify which dependency is degraded.

#### Scenario: Dependencies map carries canonical names

- **WHEN** the health endpoint is queried
- **THEN** the response body MUST include `dependencies` with keys `mongo`, `redis`, `vector_store`, `llm`, each mapped to one of `"healthy"`, `"degraded"`, `"down"`

### Requirement: Health endpoint reports circuit breaker state

The AI engine MUST expose every named circuit breaker's state in the health response.

#### Scenario: Circuit breaker map present

- **WHEN** the health endpoint is queried
- **THEN** the response body MUST include `circuit_breakers` mapping each breaker name to one of `"closed"`, `"open"`, `"half_open"`

### Requirement: Existing fields are preserved

The AI engine MUST keep the existing `services` map and `reranker_enabled` field on the health response for one release cycle so consumers reading those fields continue to work.

#### Scenario: Legacy fields still present

- **WHEN** the health endpoint is queried
- **THEN** the response body MUST still include `services` (with `vector_store` and `llm`) and `reranker_enabled`
