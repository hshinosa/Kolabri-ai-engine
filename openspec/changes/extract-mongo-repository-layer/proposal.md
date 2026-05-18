## Why

`app/services/plan_vs_reality.py` (708 LOC) and `app/services/process_mining_anomaly.py` (770 LOC) embed direct Mongo collection queries inline with analytics math. Examples: `orchestration.py:366-374` constructs raw `find_one({"CaseID": {"$regex": ...}})` queries; the same patterns are duplicated inside `plan_vs_reality.py`. This entanglement makes both files hard to unit-test (each test must mock Mongo) and hard to evolve (changing the query shape requires reading the math). Slice S6 in `improve-ai-engine-testability-and-maintainability` § G calls for repository extraction.

## What Changes

- Introduce `app/services/repositories/activity_log_repository.py` containing a thin async repository class:
  - `get_latest_session_for_group(group_id) -> Optional[str]`
  - `get_first_activity(case_id) -> Optional[dict]`
  - `get_last_activity(case_id) -> Optional[dict]`
  - `get_activities_for_case(case_id, since=None) -> list[dict]`
  - Other read shapes used by `plan_vs_reality.py` and `process_mining_anomaly.py`.
- Update `plan_vs_reality.py`, `process_mining_anomaly.py`, and the relevant section of `orchestration.py` to depend on the repository instead of `mongo_logger.db.activity_logs.*` directly.
- Analytics math stays in the original modules — only the query shape moves.

## Capabilities

### Modified Capabilities

- `ai-engine-service-maintainability` — adds the requirement that Mongo activity-log query shape lives in a thin repository, not inline with analytics modules.

## Impact

- `app/services/repositories/__init__.py`, `activity_log_repository.py` — new files.
- `app/services/plan_vs_reality.py`, `process_mining_anomaly.py`, `orchestration.py` — replace inline Mongo query construction with repository calls.
- `tests/test_unit/test_activity_log_repository.py` — new test file with mocked Motor client.
