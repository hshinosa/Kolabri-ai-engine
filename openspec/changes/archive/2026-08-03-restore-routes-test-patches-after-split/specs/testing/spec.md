# Routes Integration Test Patch Targets

## ADDED Requirements

### Requirement: Test patches SHALL target the submodule that imports the symbol

Tests in `tests/test_unit/test_routes_integration.py` SHALL use `@patch('app.api.routes.<submodule>.<name>')` for every service factory or stdlib helper that was imported into a specific route submodule (e.g. `routes/health.py`, `routes/documents.py`).

Tests SHALL NOT use `@patch('app.api.routes.<name>')` for these symbols, because the routes package aggregator does not re-export them.

#### Scenario: Patching `get_monitor` for the metrics endpoint

- Given `routes/monitoring.py` imports `get_monitor` from `app.services.monitoring`
- And the `/metrics` endpoint is defined in `routes/monitoring.py`
- When a test patches `get_monitor` to make it raise
- Then the test MUST use `@patch('app.api.routes.monitoring.get_monitor')`
- And the patched mock MUST be active during the request through `/metrics`
- And the test MUST observe the failure path (HTTP 500 with sanitized error)

#### Scenario: Patching `get_orchestrator` for groups endpoints

- Given `routes/groups.py` imports `get_orchestrator` from `app.services.orchestration`
- And the `/api/groups/{id}/dashboard` endpoint is defined in `routes/groups.py`
- When a test for that endpoint patches `get_orchestrator`
- Then the test MUST use `@patch('app.api.routes.groups.get_orchestrator')`
- And the test MUST NOT use `@patch('app.api.routes.get_orchestrator')`

#### Scenario: Aggregator-level re-exports remain stable for `settings` and background helpers

- Given the routes aggregator re-exports `settings`, `_process_ingest_background`, `_process_batch_file_background`, `ingest_document`, `ingest_batch`
- When a test patches one of these names
- Then `@patch('app.api.routes.<name>')` MUST continue to work
- Because the aggregator intentionally re-exports them
