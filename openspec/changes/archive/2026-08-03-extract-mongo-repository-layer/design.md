## Context

Today, `mongo_logger.db.activity_logs.find_one(...)` and `find(...)` calls are scattered. A grep on `orchestration.py` alone shows 3 raw query constructions (lines 366, 372, 374) using `{"CaseID": {"$regex": ...}}`. The same regex pattern is duplicated in `plan_vs_reality.py`. This is the textbook case for a repository.

## Goals / Non-Goals

**Goals:**
- One module owns the Mongo activity-log query shape.
- Analytics modules call typed methods, not inline `find_one`.
- Repository is mockable: tests pass a fake repository, no Motor required.

**Non-Goals:**
- Changing the Mongo schema.
- Changing what the analytics modules compute.
- Replacing Motor.

## Decisions

### D1: Repository per collection
`ActivityLogRepository` covers the `activity_logs` collection only. If `silence_events` or other collections need similar treatment later, they get their own repository.

### D2: Async, motor-backed
Constructor takes a Motor `AsyncIOMotorDatabase` (or `MongoDBLogger.db`). Methods are `async`. Matches existing call patterns.

### D3: Return raw dicts, not domain entities
The repository is a thin shape adapter, not a domain layer. Callers continue to read raw fields. No Pydantic model is introduced for activity logs in this slice.

## Risks / Trade-offs

- **Risk: too many methods** — Mitigation: add only the methods that have a current call site. No speculative API.
- **Risk: missed call sites** — Mitigation: grep `activity_logs\.\(find\|find_one\|insert_one\|update_one\)` after refactor; expect zero hits outside the repository file.

## Open Questions

- None.
