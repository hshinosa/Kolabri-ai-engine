## 1. OCR Import Resilience (env/dependency - 5 failures)

### Background
Five tests fail due to Python 3.13 + paddle 3.0.0 circular import errors when attempting real paddle imports. Production code already has resilient import handling; tests need to mock or skip broken imports.

- [x] 1.1 Fix test_document_processor_ocr_available_when_paddle_and_paddleocr_present
  - **Test:** `tests/test_unit/test_coverage_to_100.py::test_document_processor_ocr_available_when_paddle_and_paddleocr_present`
  - **Source:** `app/services/document_processor.py:54` (paddleocr import with try/except)
  - **Category:** env/dependency
  - **Current failure:** `AttributeError: partially initialized module 'paddle' has no attribute 'tensor'`
  - **Steps:**
    - Read test code to understand current import attempt
    - Review `test_ocr_import_branch_without_paddle_dependency` for reference mocking pattern
    - Mock `paddle` module at import level using `unittest.mock.patch` or `pytest.monkeypatch`
    - Mock should simulate successful paddle import (set `paddle` module attributes as needed)
    - Update test to use mock instead of attempting real paddle import
    - Run test to verify it passes with mocked paddle

- [x] 1.2 Fix test_document_processor_ocr_false_when_paddleocr_without_paddle
  - **Test:** `tests/test_unit/test_coverage_to_100.py::test_document_processor_ocr_false_when_paddleocr_without_paddle`
  - **Source:** `app/services/document_processor.py:54` (OCR_AVAILABLE flag logic)
  - **Category:** env/dependency
  - **Current failure:** `AttributeError` when attempting real paddle import to test negative case
  - **Steps:**
    - Read test code to understand negative case logic
    - Mock paddle import to raise `ImportError` or `AttributeError` to simulate missing paddle
    - Verify test checks `OCR_AVAILABLE=False` when paddle import fails
    - Ensure mock prevents real paddle import attempt
    - Run test to verify it passes with mocked import failure

- [x] 1.3 Fix test_image_extraction_ocr_available_when_paddle_present
  - **Test:** `tests/test_unit/test_coverage_to_100.py::test_image_extraction_ocr_available_when_paddle_present`
  - **Source:** `app/services/document_processing/image_extraction.py` (paddle import with try/except)
  - **Category:** env/dependency
  - **Current failure:** `AttributeError: partially initialized module 'paddle' has no attribute 'pir'`
  - **Steps:**
    - Read test code and image_extraction.py import logic
    - Apply same mocking pattern as 1.1 above
    - Mock paddle module to simulate successful import
    - Verify test checks `OCR_AVAILABLE=True` when paddle mock is present
    - Run test to verify it passes with mocked paddle

- [x] 1.4 Fix test_ocr_import_branch_without_paddle_dependency
  - **Test:** `tests/test_unit/test_document_processor_full.py::TestModuleLevelImports::test_ocr_import_branch_without_paddle_dependency`
  - **Source:** `app/services/document_processor.py:54` (paddleocr import try/except)
  - **Category:** env/dependency
  - **Current failure:** `AttributeError` from circular import
  - **Steps:**
    - Read test code - this test SHOULD already use proper mocking (it's mentioned as reference)
    - Identify why current mocking isn't preventing circular import
    - Ensure paddle is mocked BEFORE any import attempt (use `patch` at module import time)
    - This test should serve as the reference pattern for tests 1.1-1.3
    - If test already has correct pattern but still fails, investigate mock scope/timing
    - Run test to verify it passes; use its pattern for other tests

- [x] 1.5 Fix additional paddle circular import test variant
  - **Test:** (Fifth test in paddle circular import cluster - exact node ID to be confirmed from full pytest output)
  - **Source:** `app/services/document_processor.py` or `image_extraction.py` (paddle import sections)
  - **Category:** env/dependency
  - **Current failure:** Circular import → `AttributeError`
  - **Steps:**
    - Confirm exact test node ID from pytest failure list
    - Determine if this is a duplicate of tests 1.1-1.4 or a separate test case
    - Apply same mocking pattern as established in tests above
    - Run test to verify it passes with mocked paddle

## 2. Socratic Hint Test Alignment (stale-test - 6 failures)

### Background
Five tests check for old Indonesian keywords that are no longer present in current production hint copy. One test uses plain MagicMock for an async dependency. Production code is correct; tests need updating.

- [x] 2.1 Fix test_specific_hint
  - **Test:** `tests/test_unit/test_intervention_and_goals.py::TestGenerateSocraticHint::test_specific_hint`
  - **Source:** `app/services/goal_validator.py:641-645` (specific_hints list)
  - **Category:** stale-test-vs-new-code
  - **Current failure:** Test expects 'konkret' or 'langkah' keywords; actual hint: "Bisa lebih spesifik tentang bagian mana dari topik ini yang ingin kamu kuasai?"
  - **Current production hint keywords:** 'spesifik', 'bagian', 'kuasai'
  - **Steps:**
    - Read test assertion code to see current keyword checks
    - Read goal_validator.py lines 641-645 to confirm exact hint strings
    - Update test assertion to check for keywords present in current copy: 'spesifik', 'bagian', 'topik', 'kuasai'
    - Remove assertions for old keywords 'konkret', 'langkah'
    - Run test to verify it passes with updated keyword checks

- [x] 2.2 Fix test_measurable_hint
  - **Test:** `tests/test_unit/test_intervention_and_goals.py::TestGenerateSocraticHint::test_measurable_hint`
  - **Source:** `app/services/goal_validator.py:658-663` (measurable_hints list)
  - **Category:** stale-test-vs-new-code
  - **Current failure:** Test expects 'tahu' or 'paham' keywords; actual hint mentions 'indikator'
  - **Current production hint example:** "Indikator apa yang bisa kamu pakai untuk menilai pemahamanmu — misalnya bisa menjelaskan ke teman, atau mengerjakan soal latihan?"
  - **Current production hint keywords:** 'indikator', 'ukur', 'menilai', 'paham' (check if 'paham' is present)
  - **Steps:**
    - Read test assertion code
    - Read goal_validator.py lines 658-663 for all measurable hint strings
    - Update test to check for 'indikator', 'menilai', 'pemahamanmu' or other keywords present in current copy
    - Remove old keyword assertions for 'tahu' if not present
    - Run test to verify it passes

- [x] 2.3 Fix test_time_bound_hint
  - **Test:** `tests/test_unit/test_intervention_and_goals.py::TestGenerateSocraticHint::test_time_bound_hint`
  - **Source:** `app/services/goal_validator.py:671-676` (time_hints list)
  - **Category:** stale-test-vs-new-code
  - **Current failure:** Test expects 'kapan' or 'berencana' keywords; actual hint: "Berapa lama waktu yang akan kamu alokasikan untuk mencapai target ini?"
  - **Current production hint keywords:** 'Berapa lama', 'waktu', 'alokasikan', 'target'
  - **Steps:**
    - Read test assertion code
    - Read goal_validator.py lines 671-676 for all time_bound hint strings
    - Update test to check for 'Berapa lama', 'waktu', 'alokasikan' or other keywords in current copy
    - Remove old keyword assertions for 'kapan', 'berencana' if not present
    - Run test to verify it passes

- [x] 2.4 Fix test_achievable_hint
  - **Test:** `tests/test_unit/test_intervention_and_goals.py::TestGenerateSocraticHint::test_achievable_hint`
  - **Source:** `app/services/goal_validator.py:688-692` (achievable_hints list)
  - **Category:** stale-test-vs-new-code
  - **Current failure:** Test expects 'sumber' or 'cukup' keywords; actual hint: "Apakah target ini sudah pas untuk satu sesi diskusi, atau perlu dipecah jadi beberapa langkah?"
  - **Current production hint keywords:** 'target ini sudah pas', 'satu sesi diskusi', 'dipecah', 'langkah'
  - **Steps:**
    - Read test assertion code
    - Read goal_validator.py lines 688-692 for all achievable hint strings
    - Update test to check for 'target ini sudah pas', 'sesi diskusi', 'dipecah', 'langkah'
    - Remove old keyword assertions for 'sumber', 'cukup' if not present
    - Run test to verify it passes

- [x] 2.5 Fix test_multiple_missing_uses_first
  - **Test:** `tests/test_unit/test_intervention_and_goals.py::TestGenerateSocraticHint::test_multiple_missing_uses_first`
  - **Source:** `app/services/goal_validator.py:705-711` (primary_missing selection + hint generation)
  - **Category:** stale-test-vs-new-code
  - **Current failure:** Similar to test_time_bound_hint - expects old time_bound keywords 'kapan', 'berencana'
  - **Steps:**
    - Read test code to understand which criterion it tests as "first" (likely time_bound based on failure)
    - Verify the test checks that only ONE hint is returned for the first missing criterion
    - Update keyword assertions to match current production copy for whichever criterion is tested
    - If testing time_bound hints, use same keyword updates as task 2.3
    - Run test to verify it passes

- [x] 2.6 Fix test_validate_goal_invalid_resets_streak (async mock)
  - **Test:** `tests/test_unit/test_orchestration_coverage.py::test_validate_goal_invalid_resets_streak`
  - **Source:** (Production code with async dependency - exact file to be determined from test code inspection)
  - **Category:** stale-test-vs-new-code (sync dependency became async)
  - **Current failure:** `TypeError: object MagicMock can't be used in 'await' expression`
  - **Steps:**
    - Read test code to identify which mock is being awaited
    - Find the line where `TypeError` occurs (likely an `await mock_something()` call)
    - Identify the mock variable that needs to be AsyncMock
    - Replace `MagicMock()` with `AsyncMock()` (import from `unittest.mock`)
    - If mock has return values or side effects, ensure they're configured for async behavior
    - Run test to verify it passes after async mock replacement

## 3. RAG Grounding and Correctness (pre-existing-bug - 4 failures)

### Background
Four tests fail due to genuine logic bugs in production code: grounding threshold evaluation, RAG scaffolding context passthrough, and week metadata filter structure. These require source code fixes, not just test updates.

- [x] 3.1 Fix grounding threshold bug (is_grounded should be False below threshold)
  - **Test:** `tests/test_unit/test_grounding_verifier_async.py::test_verify_grounding_async_marks_claims_ungrounded_below_threshold`
  - **Source:** Grounding verifier service (file TBD - search for `GroundingResult` class and threshold logic)
  - **Category:** pre-existing-bug
  - **Current failure:** `GroundingResult.is_grounded=True` when ratio is below threshold (should be False)
  - **Steps:**
    - Search codebase for `GroundingResult` class definition: `rg "class GroundingResult" --type py`
    - Search for grounding threshold comparison logic: `rg "threshold" app/services/ --type py -A 5 -B 5`
    - Read grounding verifier service file to understand threshold evaluation
    - Locate the line where `is_grounded` field is set based on ratio/threshold comparison
    - Correct the boolean logic: ensure `is_grounded=False` when `ratio < threshold`
    - Common bug patterns: inverted condition, wrong operator (>= instead of <), or missing comparison
    - Run the specific test to verify fix: `pytest tests/test_unit/test_grounding_verifier_async.py::test_verify_grounding_async_marks_claims_ungrounded_below_threshold -xvs`
    - Verify no other grounding tests are broken by the fix

- [x] 3.2 Fix RAG scaffolding passthrough (early context)
  - **Test:** `tests/test_unit/test_rag_comprehensive.py::TestRAGScaffoldingContext::test_query_passes_early_scaffolding_context`
  - **Source:** RAG query service (file TBD - search for RAG query function and scaffolding context handling)
  - **Category:** pre-existing-bug
  - **Current failure:** `assert None is not None` - early scaffolding context returns None instead of provided context
  - **Steps:**
    - Search for RAG query implementation: `rg "def.*query.*scaffolding" app/ --type py` or `rg "early_scaffolding_context" app/ --type py`
    - Read test code to understand expected scaffolding context flow
    - Trace RAG query data flow: input → processing → result construction
    - Identify where scaffolding context params are accepted but not passed to result object
    - Add `early_scaffolding_context` to result object construction/return value
    - Ensure the field is properly propagated through any intermediate data structures
    - Run test to verify: `pytest tests/test_unit/test_rag_comprehensive.py::TestRAGScaffoldingContext::test_query_passes_early_scaffolding_context -xvs`

- [x] 3.3 Fix RAG scaffolding passthrough (late context)
  - **Test:** `tests/test_unit/test_rag_comprehensive.py::TestRAGScaffoldingContext::test_query_passes_late_scaffolding_context`
  - **Source:** Same RAG query service as task 3.2
  - **Category:** pre-existing-bug
  - **Current failure:** `assert None is not None` - late scaffolding context returns None
  - **Steps:**
    - Same source file as task 3.2 (should be fixed together)
    - Add `late_scaffolding_context` to result object construction alongside early context
    - Ensure both early and late scaffolding context are passed through correctly
    - Run test to verify: `pytest tests/test_unit/test_rag_comprehensive.py::TestRAGScaffoldingContext::test_query_passes_late_scaffolding_context -xvs`
    - Run both 3.2 and 3.3 tests together to ensure both work: `pytest tests/test_unit/test_rag_comprehensive.py::TestRAGScaffoldingContext -xvs`

- [x] 3.4 Fix RAG scaffolding auto-level (no early/late style)
  - **Test:** `tests/test_unit/test_coverage_to_100.py::test_rag_scaffolding_auto_level_no_early_late_style`
  - **Source:** Same RAG query service as tasks 3.2-3.3
  - **Category:** pre-existing-bug
  - **Current failure:** `assert None is not None` - scaffolding context is None when early/late distinction not used
  - **Steps:**
    - This is likely the same scaffolding passthrough bug as 3.2-3.3
    - Verify the fix from tasks 3.2-3.3 handles auto-level case correctly
    - If auto-level uses a different code path, ensure scaffolding context is passed there too
    - Read test to understand the "no early/late style" scenario
    - Run test to verify: `pytest tests/test_unit/test_coverage_to_100.py::test_rag_scaffolding_auto_level_no_early_late_style -xvs`
    - This should pass if tasks 3.2-3.3 are correctly implemented

- [x] 3.5 Fix week metadata filter $and structure
  - **Test:** `tests/test_unit/test_week_rag.py::test_week_metadata_filter_lte`
  - **Source:** Week RAG metadata filter builder (file TBD - search for week metadata filter or week RAG implementation)
  - **Category:** pre-existing-bug
  - **Current failure:** `KeyError: '$and'` - filter builder doesn't produce expected MongoDB $and structure
  - **Steps:**
    - Search for week metadata filter builder: `rg "week.*metadata.*filter" app/ --type py` or `rg "test_week_metadata_filter_lte" tests/ --type py -A 10` to see what it tests
    - Read test code to understand expected filter structure (likely `{"$and": [{"week": {"$lte": N}}]}`)
    - Find the filter construction logic that handles `$lte` and other operators
    - Identify why `$and` key is missing: filter dict not initialized, wrong structure, or missing key
    - Common bug: trying to access `filter['$and']` before initializing `filter = {'$and': []}`
    - Fix: properly initialize `$and` structure before populating it, or use correct Mongo query builder pattern
    - Verify generated filter matches MongoDB syntax requirements
    - Run test to verify: `pytest tests/test_unit/test_week_rag.py::test_week_metadata_filter_lte -xvs`
    - Check if other operators ($gte, $eq) need similar fixes

## 4. Verification

- [x] 4.1 Run all 15 failing tests to verify fixes
  - Run the specific 15 tests that were diagnosed as failing
  - Command: `pytest tests/test_unit/test_coverage_to_100.py::test_document_processor_ocr_available_when_paddle_and_paddleocr_present tests/test_unit/test_coverage_to_100.py::test_document_processor_ocr_false_when_paddleocr_without_paddle tests/test_unit/test_coverage_to_100.py::test_image_extraction_ocr_available_when_paddle_present tests/test_unit/test_document_processor_full.py::TestModuleLevelImports::test_ocr_import_branch_without_paddle_dependency tests/test_unit/test_intervention_and_goals.py::TestGenerateSocraticHint::test_specific_hint tests/test_unit/test_intervention_and_goals.py::TestGenerateSocraticHint::test_measurable_hint tests/test_unit/test_intervention_and_goals.py::TestGenerateSocraticHint::test_time_bound_hint tests/test_unit/test_intervention_and_goals.py::TestGenerateSocraticHint::test_achievable_hint tests/test_unit/test_intervention_and_goals.py::TestGenerateSocraticHint::test_multiple_missing_uses_first tests/test_unit/test_orchestration_coverage.py::test_validate_goal_invalid_resets_streak tests/test_unit/test_grounding_verifier_async.py::test_verify_grounding_async_marks_claims_ungrounded_below_threshold tests/test_unit/test_rag_comprehensive.py::TestRAGScaffoldingContext::test_query_passes_early_scaffolding_context tests/test_unit/test_rag_comprehensive.py::TestRAGScaffoldingContext::test_query_passes_late_scaffolding_context tests/test_unit/test_coverage_to_100.py::test_rag_scaffolding_auto_level_no_early_late_style tests/test_unit/test_week_rag.py::test_week_metadata_filter_lte -xvs`
  - Verify all 15 tests pass
  - If any test still fails, revisit the corresponding task and investigate further

- [x] 4.2 Run full test suite to verify no regressions
  - Run complete test suite: `pytest` (or `pytest tests/test_unit/` for unit tests only)
  - Verify test count: 2452 passed, 0 failed (was 2437 passed, 15 failed before fixes)
  - Check for any new failures introduced by the fixes
  - If new failures appear, determine if they're related to the changes and fix accordingly
  - Confirm test suite health is fully restored
