## 1. Pre-flight

- [x] 1.1 Run baseline: `pytest tests/ -q` — 2027 passing
- [x] 1.2 Audit remaining excepts: `grep -c "except Exception as e" app/api/routes/*.py`
- [x] 1.3 Identify Pattern A/B/C count per file

## 2. Pattern A: Re-raise blocks

- [x] 2.1 analytics.py: 3 CSV export endpoints — replace `except Exception as e` + `logger.error(..., error=str(e))` + `raise` with `except Exception` + `logger.exception(...)` + `raise`

## 3. Pattern B: Structured response blocks

- [x] 3.1 chat.py: 3 blocks (ask_question, personal_chat, stream)
- [x] 3.2 analytics.py: 3 blocks (engagement, group_analytics_alias, process_mining_general)
- [x] 3.3 documents.py: 4 blocks (ingest, batch, etc.)
- [x] 3.4 groups.py: 4 blocks (status, track-participation, last-message, topic)
- [x] 3.5 interventions.py: 3 blocks (analyze, summary, prompt)
- [x] 3.6 orchestration.py: 1 block

For each: replace `error=str(e)` in response body with generic "Internal error" or similar safe message.

## 4. Pattern C: Health check (5 blocks)

- [x] 4.1 health.py: replace `except Exception as e: logger.error(..., error=str(e))` with `except Exception: logger.exception(...)` for consistency
- [x] 4.2 Verify dependencies/circuit_breakers status logic still works

## 5. Update affected tests

- [x] 5.1 Audit test assertions: `grep -rn '"error":' tests/`
- [x] 5.2 Update tests yang assert specific error string dalam response body
- [x] 5.3 Tests yang assert `success=False` tetap valid

## 6. Verify

- [x] 6.1 `pytest tests/ -q` — passing
- [x] 6.2 `openspec validate improve-route-logging-and-narrow-excepts --strict`
- [x] 6.3 `grep "error=str(e)" app/api/routes/*.py` — 0 matches in response bodies (logging-only OK)
- [x] 6.4 Manual test: trigger error, verify response body doesn't contain stack trace
