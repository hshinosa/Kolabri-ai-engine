# Service Layer Error Sanitization

## ADDED Requirements

### Requirement: Service result objects SHALL contain safe error messages

Service modules in `app/services/` that return result objects (Pydantic models, dataclasses) with an `error` field SHALL ensure the `error` field contains only user-safe messages, never raw `str(e)` from caught exceptions.

#### Scenario: RAG pipeline error

- Given `app/services/rag.py` catches an exception during query processing
- When constructing `RAGResult` with `success=False`
- Then `error` field MUST contain a generic safe message (e.g., "Internal error")
- And it MUST NOT contain `str(e)` from the caught exception
- And the full exception details MUST be logged via `logger.exception(...)` with structured context

#### Scenario: Orchestrator dashboard error

- Given `app/services/orchestration.py` catches an exception
- When constructing a result with error info
- Then the error field MUST contain a safe message
- And `str(e)` MUST NOT propagate to the result object

### Requirement: Service result objects SHALL document safe-by-construction contract

Result dataclasses with `error: Optional[str]` field SHALL include a docstring documenting that `error` contains only user-safe messages. This communicates the contract to route handlers that consume the result.

#### Scenario: Result class documentation

- Given a service result class with an `error` field
- When the class is defined
- Then it MUST have a docstring stating: "error field contains user-safe messages only; internal details logged via logger.exception, not exposed"
