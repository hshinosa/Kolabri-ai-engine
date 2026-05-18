# Routes __init__.py Cleanup

## MODIFIED Requirements

### Requirement: routes/__init__.py SHALL be a pure aggregator

`app/api/routes/__init__.py` SHALL contain only router imports and `include_router` calls. It MUST NOT define endpoints, helper functions, or business logic.

#### Scenario: Aggregator file content

- Given `app/api/routes/__init__.py`
- When the file is read
- Then it MUST contain only: imports of per-capability routers, the parent `APIRouter()` instance, and `router.include_router(...)` calls
- And it MUST NOT contain `@router.get/post/put/delete/...` decorators
- And it MUST NOT contain top-level functions other than imports and the router instance

#### Scenario: DI helpers moved to dependencies module

- Given a route module needs `get_vector_store` or `get_llm_service`
- When the module declares its imports
- Then it MUST import from `app.api.dependencies` (or directly from the service module)
- And it MUST NOT import from `app.api.routes` aggregator
