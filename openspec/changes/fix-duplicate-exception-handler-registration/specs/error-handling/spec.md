# Exception Handler Registration

## MODIFIED Requirements

### Requirement: Single source of truth for exception handlers

`main.py` SHALL register each exception class with at most one handler. Handler logic SHALL live in `app/core/error_handlers.py`, not inline in `main.py`.

#### Scenario: No duplicate registration

- Given `main.py` registers exception handlers
- When the same exception class (e.g., `StarletteHTTPException`) is registered
- Then it MUST be registered exactly once
- And the registration MUST be via `app.add_exception_handler(...)` referencing a function in `app/core/error_handlers.py`
- And `main.py` MUST NOT contain `@app.exception_handler(...)` decorators for `Exception`, `StarletteHTTPException`, or `RequestValidationError`

#### Scenario: Domain-specific handlers stay in main.py

- Given a domain-specific exception (e.g., `LLMDegradedError`)
- When the handler is unique to one domain and not generalized
- Then it MAY remain in `main.py` as a `@app.exception_handler(...)` decorator
- But it MUST NOT shadow handlers registered via `add_exception_handler`
