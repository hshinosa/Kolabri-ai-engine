## ADDED Requirements

### Requirement: Inbound requests are assigned a stable correlation id

The AI engine MUST assign every inbound HTTP request a stable correlation id (`request_id`) that survives across logging, response shaping, and persistence boundaries within that request.

#### Scenario: Request without upstream id receives a new one

- **WHEN** an inbound request arrives without an `X-Request-ID` header
- **THEN** the system MUST generate a fresh UUID-shaped `request_id` and bind it for the duration of the request

#### Scenario: Valid upstream id is reused

- **WHEN** an inbound request carries an `X-Request-ID` header whose value parses as a UUID
- **THEN** the system MUST reuse that value as the `request_id` for the request

#### Scenario: Invalid upstream id is replaced

- **WHEN** an inbound request carries an `X-Request-ID` header whose value does not parse as a UUID
- **THEN** the system MUST generate a fresh UUID-shaped `request_id` and discard the upstream value

### Requirement: Logs emitted during a request carry the correlation id

The AI engine MUST attach the request's `request_id` to every structured log line emitted during that request without requiring explicit threading at the call site.

#### Scenario: Service-layer log line is correlatable

- **WHEN** any code path emits a `structlog`-based log line during request processing
- **THEN** that log line MUST include the `request_id` bound for the request

### Requirement: Error responses surface the correlation id

The AI engine MUST surface the `request_id` in the JSON body of error responses produced by the global, HTTP, and validation exception handlers.

#### Scenario: Unhandled exception surfaces the id

- **WHEN** an unhandled exception is converted to a 500 response
- **THEN** the response body MUST include `request_id` and MUST keep the existing `detail` and `message` fields unchanged

#### Scenario: HTTP exception surfaces the id

- **WHEN** an `HTTPException` is converted to its response
- **THEN** the response body MUST include `request_id` and MUST keep its existing fields unchanged

#### Scenario: Validation error surfaces the id

- **WHEN** a request fails Pydantic validation and the validation exception handler runs
- **THEN** the response body MUST include `request_id`

### Requirement: Response header echoes the correlation id

The AI engine MUST set `X-Request-ID` on every outbound HTTP response so callers can correlate a response to its server-side logs without inspecting the body.

#### Scenario: Successful response carries the id in header

- **WHEN** a request completes successfully
- **THEN** the response MUST include `X-Request-ID: <request_id>` in its headers

#### Scenario: Error response carries the id in header

- **WHEN** a request completes with an error response
- **THEN** the response MUST include `X-Request-ID: <request_id>` in its headers

### Requirement: Activity logs persist the correlation id

The AI engine MUST persist the request's `request_id` into Mongo activity-log documents written during that request.

#### Scenario: Activity log written during request

- **WHEN** any code path during request processing calls `MongoLogger.log_activity(...)`
- **THEN** the persisted document MUST include `request_id` matching the request's bound id
