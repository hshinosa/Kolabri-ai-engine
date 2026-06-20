## Context

The ai-engine test suite currently has 15 failing tests out of 2452 total. These failures were diagnosed after a full pytest run and fall into three distinct root-cause categories:

1. **Environment/dependency issues (5 failures)**: Tests that check OCR availability by importing `paddle`/`paddleocr` fail under Python 3.13 with paddle 3.0.0 due to circular import errors (`AttributeError: partially initialized module 'paddle'... has no attribute 'tensor'/'pir'`). The production code already has resilient import handling with `OCR_AVAILABLE` flags and try/except guards, but the tests themselves attempt real imports and break.

2. **Stale test assertions (6 failures)**: Tests in `test_intervention_and_goals.py::TestGenerateSocraticHint` verify Indonesian hint copy by checking for specific keywords. The production Socratic hint strings in `goal_validator.py` were updated but the test keyword assertions were not updated to match. Additionally, one test in `test_orchestration_coverage.py` uses a plain `MagicMock` for an async dependency that became async after the test was written.

3. **Pre-existing logic bugs (4 failures)**: 
   - Grounding verifier marks claims as `is_grounded=True` even when ratio is below threshold
   - RAG query path returns `None` for scaffolding context instead of passing through early/late context
   - Week metadata filter builder raises `KeyError: '$and'` instead of producing expected Mongo filter structure
   - All three represent actual logic bugs, not test issues

Current project constraints: Python 3.13, paddle 3.0.0, pytest test suite. The fixes must not change production behavior except where logic is genuinely broken (category 3).

## Goals / Non-Goals

**Goals:**
- Restore test suite to 100% pass rate (2452 passing, 0 failing)
- Classify each failure by accurate root cause (env/dependency, stale-test, pre-existing-bug)
- Fix environment/dependency tests to mock or skip broken imports rather than importing real broken paddle
- Align stale test assertions with current production copy without changing production unless production is wrong
- Correct pre-existing logic bugs in grounding threshold, RAG scaffolding passthrough, and week metadata filter
- Provide concrete file:line references for every test failure and source touchpoint

**Non-Goals:**
- Changing production Socratic hint copy (assume current copy is correct unless investigation proves otherwise)
- Upgrading or downgrading paddle/paddleocr dependencies (OCR is optional; tests should handle import failures gracefully)
- Refactoring test structure beyond what's needed to fix the specific failures
- Adding new test coverage or removing existing tests
- Performance optimization or code cleanup unrelated to the 15 diagnosed failures

## Decisions

### Decision 1: Group failures into 3 capabilities by root cause

**Rationale:** The 15 failures have distinct root causes requiring different fix strategies. Grouping by root cause (env/dependency, stale-test, pre-existing-bug) makes the fix approach clear and ensures each failure is addressed with the correct strategy.

**Capability grouping:**
- `ocr-import-resilience`: 5 env/dependency failures (paddle circular import under py3.13)
- `socratic-hint-test-alignment`: 6 stale-test failures (5 hint keyword mismatches + 1 async mock)
- `rag-grounding-and-correctness`: 4 pre-existing logic bugs (grounding threshold, RAG scaffolding x2, week filter, async mock)

Wait - the async mock failure (`test_validate_goal_invalid_resets_streak`) is a stale-test issue (sync became async), not a logic bug. I'll move it to `socratic-hint-test-alignment` even though it's not about Socratic hints - it's still a stale-test-vs-new-code issue where a mock needs updating.

Actually, let me reconsider the grouping. The assignment says:
- env/dependency: 5 paddle failures
- stale-test-vs-new-code: 5 Socratic hint failures
- pre-existing-bug: 5 failures (grounding, RAG scaffolding x2, week filter, async mock)

But the async mock failure is listed under "pre-existing-bug / logic" with note "Category: stale-test-vs-new-code (a sync dep became async)". So there's ambiguity. Let me follow the assignment's initial categorization and note the async mock as stale-test in the description.

Actually, re-reading the assignment more carefully:
- env/dependency: 5 paddle failures (clearly stated)
- stale-test-vs-new-code: 5 Socratic hint failures (clearly stated)
- pre-existing-bug / logic: 5 failures listed, but the last one (async mock) has a note saying "Category: stale-test-vs-new-code"

So the count is:
- env/dependency: 5
- stale-test-vs-new-code: 5 + 1 = 6
- pre-existing-bug: 4

Total: 15. This matches.

So the capability grouping should be:
- `ocr-import-resilience`: 5 env/dependency failures
- `socratic-hint-test-alignment`: 6 stale-test failures (5 hint + 1 async mock)
- `rag-grounding-and-correctness`: 4 pre-existing logic bugs

Let me continue writing the design with this corrected grouping.

**Alternatives considered:**
- Group by affected module (document_processor, goal_validator, RAG, grounding): Rejected because it would mix root causes and fix strategies, making it harder to apply the right fix to each failure.
- Group all as one capability: Rejected because 15 heterogeneous failures with 3 distinct fix strategies is too broad for a single spec.

### Decision 2: OCR import tests should mock paddle or skip when broken

**Rationale:** The production code in `document_processor.py` and `image_extraction.py` already has resilient import handling:
```python
try:
    from paddleocr import PaddleOCR
    OCR_AVAILABLE = True
except Exception as e:
    OCR_AVAILABLE = False
    OCR_IMPORT_ERROR = str(e)
```

The tests that verify OCR availability (`test_document_processor_ocr_available_when_paddle_and_paddleocr_present`, etc.) attempt real imports of paddle and fail under py3.13 + paddle 3.0.0 due to circular imports. The fix is to mock `paddle` at the import level or skip tests when paddle is genuinely broken in the environment, rather than letting the circular import propagate into the test suite.

**Fix strategy:**
- Investigate how existing branch-guard tests mock paddle imports (e.g., `test_ocr_import_branch_without_paddle_dependency`)
- Apply the same mocking pattern to the 5 failing tests
- Alternatively, use `pytest.mark.skipif` to skip when paddle import raises AttributeError
- Do NOT change production import guards (they are already correct)

**Alternatives considered:**
- Downgrade paddle or upgrade to a fixed version: Rejected because OCR is optional and the version constraint may be external.
- Remove the tests: Rejected because they verify important branch coverage.

### Decision 3: Socratic hint tests should match current production copy

**Rationale:** The Socratic hint strings in `goal_validator.py` (lines 643, 660, 673, 690) are the source of truth. The tests verify that hints are generated correctly for each missing SMART criterion. When the Indonesian copy changed, the test keyword assertions became stale.

**Current production hints (from goal_validator.py:609-712):**
- `specific`: "Bisa lebih spesifik tentang bagian mana dari topik ini yang ingin kamu kuasai?"
- `measurable`: "Indikator apa yang bisa kamu pakai untuk menilai pemahamanmu..."
- `time_bound`: "Berapa lama waktu yang akan kamu alokasikan untuk mencapai target ini?"
- `achievable`: "Apakah target ini sudah pas untuk satu sesi diskusi, atau perlu dipecah jadi beberapa langkah?"

**Test expectations (stale):**
- `test_specific_hint`: expects 'konkret'/'langkah' - NOT in current copy
- `test_measurable_hint`: expects 'tahu'/'paham' - NOT in current copy (now says 'indikator')
- `test_time_bound_hint`: expects 'kapan'/'berencana' - NOT in current copy (now says 'Berapa lama')
- `test_achievable_hint`: expects 'sumber'/'cukup' - NOT in current copy (now says 'Apakah target ini sudah pas')

**Fix strategy:**
- Read the exact hint strings from goal_validator.py for each SMART criterion
- Update test keyword assertions to match current copy (e.g., check for 'indikator' instead of 'tahu'/'paham')
- Do NOT change production hint copy unless investigation shows it's semantically wrong

**Alternatives considered:**
- Change production copy to match tests: Rejected because we assume current copy is correct (assignment says "assume current copy is correct unless investigation proves otherwise").
- Remove keyword assertions entirely: Rejected because they provide useful validation that the right hint type is returned.

### Decision 4: Async mock correction is a test update, not a logic bug

**Rationale:** The failure `test_validate_goal_invalid_resets_streak` raises `TypeError: object MagicMock can't be used in 'await' expression`. This happens when a dependency that was synchronous became async, but the test mock was not updated. This is a stale-test issue, not a production logic bug.

**Fix strategy:**
- Identify the mock that needs to be AsyncMock instead of MagicMock
- Replace `MagicMock()` with `AsyncMock()` in the test setup
- Verify the test passes after the mock type change

**Alternatives considered:**
- Classify as pre-existing-bug: Rejected because the production code is correct; only the test mock is wrong.

### Decision 5: Pre-existing logic bugs require source code fixes

**Rationale:** The 4 remaining failures represent actual logic bugs in production:
1. **Grounding threshold**: `GroundingResult.is_grounded=True` when ratio is below threshold (should be False)
2. **RAG scaffolding passthrough (2 tests)**: Query returns `None` for scaffolding context instead of passing through early/late context
3. **Week metadata filter**: Raises `KeyError: '$and'` instead of producing expected Mongo filter structure

These are not test issues; the production logic is broken. The fixes require:
- Reading the grounding verifier source to understand threshold evaluation logic
- Reading the RAG query path to understand scaffolding context handling
- Reading the week metadata filter builder to understand Mongo query construction
- Correcting the logic in each source file
- Verifying tests pass after the fix

**Fix strategy:**
- Identify exact source file:line for each bug
- Implement minimal fix to correct the logic
- Run the specific failing tests to verify the fix
- Do NOT refactor or optimize beyond the minimal fix

**Alternatives considered:**
- Update tests to match broken behavior: Rejected because these are genuine bugs where production logic is wrong.
- Defer fixes to separate change: Rejected because these failures block the test suite now and are already diagnosed.

## Risks / Trade-offs

**Risks:**
- **Paddle version compatibility**: Mocking paddle imports may not test the actual OCR code path in environments where paddle works. If paddle is fixed in a future version, we may not notice. *Mitigation:* Keep the tests but make them resilient to import failures; run in environments where paddle works when possible.
- **Socratic hint copy churn**: If the Indonesian copy changes frequently, tests will need frequent updates. *Mitigation:* Consider using more flexible assertions (check for key concepts rather than exact keywords) if churn becomes a problem. For this change, exact keyword matching is acceptable.
- **Logic bug fixes may have unintended effects**: Correcting the grounding threshold, RAG scaffolding, or week filter logic may reveal other bugs or change behavior in unexpected ways. *Mitigation:* Run full test suite after fixes; review production usage of these components if available.

**Trade-offs:**
- **Mocking vs. real imports**: Mocking paddle imports means we're not testing the real import path. This is acceptable because OCR is optional and the production code already has resilient import handling.
- **Keyword matching vs. semantic validation**: Tests check for specific keywords in hints rather than validating semantic correctness. This is fast and deterministic but brittle to copy changes. For this change, we accept the brittleness and update keywords to match current copy.
- **Minimal fixes vs. refactoring**: We're fixing only the diagnosed issues without broader refactoring. This is faster and lower-risk but may leave related issues unfixed. For this change, scope is limited to the 15 diagnosed failures.
