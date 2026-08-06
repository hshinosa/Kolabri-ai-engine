## ADDED Requirements

### Requirement: API surface is partitioned by capability

The AI engine MUST expose its HTTP API through per-capability modules under `app/api/routes/`, where each module owns the routes for one capability tag.

#### Scenario: Each capability has its own module

- **WHEN** a developer needs to find or modify an endpoint
- **THEN** the endpoint MUST live in a file named after its capability (e.g. `health.py`, `analytics.py`, `documents.py`, `chat.py`, `goal.py`, `conformance.py`, `track_activity.py`)

#### Scenario: Existing import path is preserved

- **WHEN** any module imports `from app.api.routes import router`
- **THEN** the import MUST resolve to a unified `APIRouter` that includes every capability router

#### Scenario: Endpoint URLs are unchanged

- **WHEN** a request hits any endpoint that existed before the split
- **THEN** the path, method, request schema, and response schema MUST be identical to the pre-split behavior

### Requirement: No per-capability route module exceeds the size cap

The AI engine MUST keep each per-capability route module under 400 lines of code so each remains independently reviewable.

#### Scenario: Route module size cap

- **WHEN** a per-capability route module is reviewed
- **THEN** its line count MUST be under 400 LOC; further growth requires another decomposition
