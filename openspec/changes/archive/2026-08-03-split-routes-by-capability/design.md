## Context

A 1,712-LOC `routes.py` collapses too many concerns into one file. Consequences observed today: every endpoint addition (e.g. `track-activity`) modifies the same file; merge contention is high; testing requires loading the entire module to exercise one endpoint.

`tests/test_integration/test_api_routes.py:43` already imports the router via `from app.api.routes import router as api_router`. Preserving that import path is the simplest non-breaking strategy.

## Goals / Non-Goals

**Goals:**
- One module per capability under `app/api/routes/`.
- Total LOC per per-capability file < 400.
- Existing import path `from app.api.routes import router` continues to work.
- All existing integration tests pass without edits.

**Non-Goals:**
- Changing endpoint paths.
- Changing request/response schemas.
- Renaming `routes.py` to `endpoints.py` or any other directory rename.
- Touching `app/api/batch_routes.py` (already separate; only ensure the aggregator includes it).

## Decisions

### D1: Convert `routes.py` to a package
Replace `app/api/routes.py` with `app/api/routes/__init__.py` that re-exports a unified `APIRouter`. Each capability module owns its own `APIRouter` instance and the package-level `__init__.py` includes them with `router.include_router(...)`.

### D2: Capability boundary follows existing tags
The current FastAPI `tags=[...]` decorator already groups routes ("Health", "Analytics", "RAG Query", "Documents", etc.). Use those tags as the boundary; one tag → one module. This makes the split mechanical.

### D3: Auth and middleware stay in `main.py`
The `Depends(require_auth)` is applied at `main.py:166` via `app.include_router(api_router, prefix="/api", dependencies=[Depends(require_auth)])`. That stays. Per-capability routers are pure routing definitions.

### D4: Order endpoints in each module by route, not by HTTP method
Read order matches URL order (e.g. `GET /documents` before `POST /documents` before `DELETE /documents/{id}`).

## Risks / Trade-offs

- **Risk: circular imports** — some endpoints import service singletons that import routes elsewhere. Mitigation: services should never import from `app.api.*`. If they do, the violation surfaces here and gets fixed.
- **Risk: shared private helpers** — internal functions like `_validate_payload` may be reused by multiple endpoints. Mitigation: move them into `app/api/_helpers.py` (one private module).
- **Risk: integration test fixture loads only `test_api_routes.py` style** — verified that the fixture imports `app.api.routes` (line 43) which we preserve.

## Open Questions

- None.
