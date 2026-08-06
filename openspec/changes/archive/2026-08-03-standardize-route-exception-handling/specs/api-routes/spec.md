# Route Exception Handling Standardization

## ADDED Requirements

### Requirement: Global exception handler for unhandled errors

The application SHALL register a global exception handler that catches unhandled exceptions and returns a generic error response without leaking implementation details.

#### Scenario: Internal server error

- Given a route handler raises an unhandled `Exception`
- When the exception propagates to the global handler
- Then the response status MUST be 500
- And the response body MUST be `{"detail": "Internal server error", "request_id": "<id>"}`
- And the full exception (with stack trace) MUST be logged with `request_id`
- And `str(exc)` MUST NOT appear in the response body

#### Scenario: HTTPException pass-through

- Given a route handler explicitly raises `HTTPException(status_code=404, detail="Not found")`
- When the exception reaches the global handler
- Then the response status MUST be 404
- And the response body MUST contain `{"detail": "Not found", "request_id": "<id>"}`

### Requirement: Pydantic validation errors return 422

When a request fails Pydantic body or path validation, the application SHALL return HTTP 422 with sanitized field-level error details.

#### Scenario: Invalid request payload

- Given a route handler with Pydantic-typed request body
- When the request payload fails validation
- Then the response status MUST be 422
- And the response body MUST include sanitized field errors
- And the response MUST include `request_id`

## MODIFIED Requirements

### Requirement: Route handlers MUST NOT catch broad Exception

Route handlers SHALL NOT use `except Exception as e: raise HTTPException(status_code=500, detail=str(e))` pattern.

#### Scenario: Service layer exception

- Given a route handler calls a service that raises an exception
- When the exception propagates
- Then the route handler MUST NOT catch it with broad `except Exception`
- And the global handler MUST handle the exception
- And `str(e)` MUST NOT be exposed to the client

#### Scenario: Specific error semantics

- Given a route needs to communicate a specific error (e.g., resource not found)
- When the condition is detected
- Then the route handler MUST raise `HTTPException(status_code=4xx, detail="<safe message>")` explicitly
- And MUST NOT use generic 500 with `str(e)`
