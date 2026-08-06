## Why

`app/api/routes.py` is 1,712 LOC and aggregates every endpoint in the AI engine: chat, RAG ask, document upload, document delete, analytics, dashboard, CSV export, conformance, goal validation, batch, health, and the recently added track-activity. The file is the single largest source file in the repository and is a cross-functional merge hotspot. The `improve-ai-engine-testability-and-maintainability` change identified this as slice S3 (§ G).

## What Changes

- Introduce `app/api/routes/` package with one module per capability:
  - `health.py` — `/health`
  - `track_activity.py` — `/track-activity`
  - `analytics.py` — engagement, dashboard, CSV exports
  - `chat.py` — chat / ask / RAG-driven endpoints
  - `documents.py` — upload, delete, ingestion
  - `goal.py` — goal validation + refinement
  - `conformance.py` — conformance + plan-vs-reality
  - `batch.py` — batch endpoints (already partially split)
- Replace the single `app/api/routes.py` with a thin aggregator that imports each per-capability `router` and re-exports a unified `router`.
- No endpoint URL changes. No request/response schema changes.

## Capabilities

### Modified Capabilities

- `ai-engine-service-maintainability` — adds the requirement that the API surface is split per capability instead of being defined in a single 1,700+ LOC file.

## Impact

- `app/api/routes.py` — becomes thin re-export module (or replaced by `app/api/routes/__init__.py`).
- `app/api/routes/<capability>.py` — new files.
- `main.py` — no change; still imports `from app.api.routes import router as api_router`.
- `tests/test_integration/test_api_routes*.py` — must continue to pass without modification.
