## ADDED Requirements

### Requirement: Grounding Verifier Must Mark Claims Below Threshold as Ungrounded

The grounding verifier service evaluates whether AI-generated claims are supported by source documents. It calculates a grounding ratio (supported claims / total claims) and SHALL mark the result as `is_grounded=False` when the ratio falls below a configurable threshold. Currently, the logic incorrectly returns `is_grounded=True` even when the ratio is below the threshold.

#### Scenario: Claims below threshold are marked ungrounded

- **WHEN** `test_verify_grounding_async_marks_claims_ungrounded_below_threshold` runs with a grounding ratio below the configured threshold (e.g., ratio=0.5 when threshold=0.7)
- **THEN** the returned `GroundingResult` should have `is_grounded=False`, not `is_grounded=True` (current buggy behavior)

**Test location:** `tests/test_unit/test_grounding_verifier_async.py::test_verify_grounding_async_marks_claims_ungrounded_below_threshold`

**Source touchpoint:** Grounding verifier service (exact file to be determined by searching for `GroundingResult` class and threshold comparison logic)

**Current failure:** Test assertion fails because `GroundingResult.is_grounded=True` when ratio is below threshold (should be `False`)

**Fix approach:**
1. Search codebase for `GroundingResult` class definition and `is_grounded` field
2. Find the threshold comparison logic (likely comparing `ratio < threshold` or similar)
3. Correct the boolean logic so `is_grounded=False` when `ratio < threshold`
4. Verify the test passes after fix
5. Consider whether there are other tests covering threshold boundary conditions

**Root cause category:** Pre-existing logic bug (grounding threshold evaluation is inverted or incorrect)

### Requirement: RAG Query Must Pass Through Scaffolding Context

The RAG (Retrieval-Augmented Generation) query path SHALL accept and pass through scaffolding context parameters (`early_scaffolding_context`, `late_scaffolding_context`) from the query input to the query results. Currently, the scaffolding context is not being passed through, resulting in `None` values in the query results even when valid context is provided.

#### Scenario: Query passes early scaffolding context to results

- **WHEN** `test_query_passes_early_scaffolding_context` runs with `early_scaffolding_context` provided in the query parameters
- **THEN** the query result should contain the provided early scaffolding context, not `None`

**Test location:** `tests/test_unit/test_rag_comprehensive.py::TestRAGScaffoldingContext::test_query_passes_early_scaffolding_context`

**Source touchpoint:** RAG query service/module (exact file to be determined by searching for RAG query implementation and scaffolding context handling)

**Current failure:** `assert None is not None` - scaffolding context is `None` in results when it should contain the provided context

**Fix approach:**
1. Search codebase for RAG query function/method that accepts scaffolding context parameters
2. Trace the data flow from query input → processing → result construction
3. Identify where scaffolding context is being dropped (not passed to result object)
4. Add scaffolding context to the result object construction
5. Verify both early and late scaffolding tests pass after fix

**Root cause category:** Pre-existing logic bug (scaffolding context passthrough not implemented)

#### Scenario: Query passes late scaffolding context to results

- **WHEN** `test_query_passes_late_scaffolding_context` runs with `late_scaffolding_context` provided in the query parameters
- **THEN** the query result should contain the provided late scaffolding context, not `None`

**Test location:** `tests/test_unit/test_rag_comprehensive.py::TestRAGScaffoldingContext::test_query_passes_late_scaffolding_context`

**Source touchpoint:** Same as early scaffolding scenario (RAG query service)

**Current failure:** `assert None is not None` - late scaffolding context is `None` in results

**Fix approach:** Same as early scaffolding fix above; both should be resolved by the same code change

**Root cause category:** Pre-existing logic bug (same as above)

#### Scenario: RAG scaffolding auto-level handles missing early/late style

- **WHEN** `test_rag_scaffolding_auto_level_no_early_late_style` runs to verify scaffolding behavior when early/late style is not specified
- **THEN** the query should handle scaffolding context correctly even when early/late distinction is not used, without returning `None` for scaffolding fields

**Test location:** `tests/test_unit/test_coverage_to_100.py::test_rag_scaffolding_auto_level_no_early_late_style`

**Source touchpoint:** Same RAG query service as above scenarios

**Current failure:** `assert None is not None` - scaffolding context is `None` when it should have a value

**Fix approach:** Same as early/late scaffolding fixes above; ensure scaffolding context is passed through regardless of early/late style specification

**Root cause category:** Pre-existing logic bug (same scaffolding passthrough issue)

### Requirement: Week Metadata Filter Must Produce Valid Mongo Query Structure

The week RAG metadata filter builder constructs MongoDB query filters to retrieve documents by week metadata. When building filters with operators like `$lte` (less than or equal), the filter builder SHALL produce a valid Mongo query structure. Currently, the builder raises an error when attempting to construct the filter.

#### Scenario: Week metadata filter constructs valid $and structure for lte operator

- **WHEN** `test_week_metadata_filter_lte` runs to verify week metadata filtering with `$lte` operator
- **THEN** the filter builder should produce a valid MongoDB query structure like `{"$and": [{"week": {"$lte": N}}]}` without raising `KeyError: '$and'`

**Test location:** `tests/test_unit/test_week_rag.py::test_week_metadata_filter_lte`

**Source touchpoint:** Week RAG metadata filter builder (exact file to be determined by searching for week metadata filter or week RAG implementation)

**Current failure:** `KeyError: '$and'` - the filter builder attempts to access or construct `$and` but the key doesn't exist or the structure is malformed

**Fix approach:**
1. Search codebase for week metadata filter builder (likely in RAG service or week-specific RAG module)
2. Find the filter construction logic that handles operators like `$lte`
3. Identify why `$and` key is missing or incorrectly constructed
4. Correct the filter builder to properly initialize and populate `$and` array structure
5. Verify the test passes and the generated filter is valid MongoDB syntax
6. Check if other operators (e.g., `$gte`, `$eq`) have the same issue and need similar fixes

**Root cause category:** Pre-existing logic bug (week metadata filter builder doesn't produce correct Mongo query structure)

### Requirement: Fixes Must Be Minimal and Targeted

All fixes for pre-existing logic bugs SHALL be minimal and targeted to the specific issue, without refactoring or optimizing code beyond what's needed to make the tests pass.

#### Scenario: Logic fixes do not introduce refactoring or scope creep

- **WHEN** grounding threshold, RAG scaffolding, or week filter logic is corrected
- **THEN** the fix should change only the minimal lines of code needed to correct the logic, without:
  - Refactoring surrounding code
  - Adding new features or abstractions
  - Changing variable names or code style
  - Optimizing performance beyond the bug fix
  - Modifying test structure beyond what's needed for the fix

**Constraint:** Minimal surgical fixes only; no scope creep beyond the 15 diagnosed test failures.
