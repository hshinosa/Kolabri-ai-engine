# Route Logging and Exception Handling Refinement

## ADDED Requirements

### Requirement: Route handlers SHALL use logger.exception for unhandled errors

Route handlers that catch exceptions for logging or graceful degradation SHALL use `logger.exception(...)` to automatically capture tracebacks, instead of `logger.error(..., error=str(e))`.

#### Scenario: Re-raise after logging

- Given a route handler catches an exception purely for logging context
- When the handler re-raises the exception
- Then it MUST use `except Exception: logger.exception("event")` followed by `raise`
- And it MUST NOT use `except Exception as e:` with `error=str(e)` in logger args

#### Scenario: Graceful degradation response

- Given a route handler catches an exception to return a structured error response
- When constructing the response body
- Then `error` field MUST contain a generic safe message (e.g., "Internal error")
- And the original exception details MUST be captured via `logger.exception(...)`
- And `str(e)` MUST NOT appear in the response body

### Requirement: Health check handlers MAY catch per-service exceptions

Health check endpoints MAY catch broad `Exception` per service ping to mark service status as "unhealthy", and they MUST log exception details via `logger.exception` and MUST NOT expose `str(e)` in the response body.

#### Scenario: Service ping failure

- Given a health check pings multiple downstream services
- When one service ping raises an exception
- Then the handler MUST mark that service as "unhealthy" in the response
- And the exception MUST be logged via `logger.exception` with service name
- And the response body MUST NOT contain `str(e)` for that service
