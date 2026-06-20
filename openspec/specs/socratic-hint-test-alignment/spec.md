# socratic-hint-test-alignment Specification

## Purpose
TBD - created by archiving change ai-engine-fix-failing-tests. Update Purpose after archive.
## Requirements
### Requirement: Socratic Hint Tests Must Match Current Production Copy

The Socratic hint generation in `app/services/goal_validator.py` produces Indonesian-language prompts to guide students when their learning goals are missing SMART criteria. When the production hint copy was updated, the test keyword assertions became stale; tests MUST assert keywords that are actually present in the current production strings, not replaced ones.

Tests MUST be updated to check for keywords that are actually present in the current production hint copy (lines 643, 660, 673, 690 in `goal_validator.py`), rather than old keywords that have been replaced.

#### Scenario: specific hint contains current copy keywords

- **WHEN** `test_specific_hint` runs to verify the hint for missing "specific" criterion
- **THEN** the test should assert that the generated hint contains keywords from the current production copy (e.g., "spesifik", "bagian", "kuasai") rather than old keywords ("konkret", "langkah") that are no longer present in the hint string

**Test location:** `tests/test_unit/test_intervention_and_goals.py::TestGenerateSocraticHint::test_specific_hint`

**Source touchpoint:** `app/services/goal_validator.py:641-645` (specific_hints list)

**Current production hint:** `"Bisa lebih spesifik tentang bagian mana dari topik ini yang ingin kamu kuasai?"`

**Current test expectation (stale):** Checks for 'konkret' or 'langkah' - neither present in current copy

**Fix approach:** Read exact hint strings from goal_validator.py:641-645; update test to check for keywords present in current copy (e.g., 'spesifik', 'bagian', 'kuasai').

#### Scenario: measurable hint contains current copy keywords

- **WHEN** `test_measurable_hint` runs to verify the hint for missing "measurable" criterion
- **THEN** the test should assert that the generated hint contains keywords from the current production copy (e.g., "indikator", "ukur", "tercapai") rather than old keywords ("tahu", "paham") that are no longer present

**Test location:** `tests/test_unit/test_intervention_and_goals.py::TestGenerateSocraticHint::test_measurable_hint`

**Source touchpoint:** `app/services/goal_validator.py:658-663` (measurable_hints list)

**Current production hint (example):** `"Indikator apa yang bisa kamu pakai untuk menilai pemahamanmu — misalnya bisa menjelaskan ke teman, atau mengerjakan soal latihan?"`

**Current test expectation (stale):** Checks for 'tahu' or 'paham' - neither present in current copy

**Fix approach:** Read exact hint strings from goal_validator.py:658-663; update test to check for 'indikator' and other keywords present in current copy.

#### Scenario: time_bound hint contains current copy keywords

- **WHEN** `test_time_bound_hint` runs to verify the hint for missing "time_bound" criterion
- **THEN** the test should assert that the generated hint contains keywords from the current production copy (e.g., "Berapa lama", "waktu", "alokasikan") rather than old keywords ("kapan", "berencana") that are no longer present

**Test location:** `tests/test_unit/test_intervention_and_goals.py::TestGenerateSocraticHint::test_time_bound_hint`

**Source touchpoint:** `app/services/goal_validator.py:671-676` (time_hints list)

**Current production hint (example):** `"Berapa lama waktu yang akan kamu alokasikan untuk mencapai target ini?"`

**Current test expectation (stale):** Checks for 'kapan' or 'berencana' - neither present in current copy

**Fix approach:** Read exact hint strings from goal_validator.py:671-676; update test to check for 'Berapa lama', 'waktu', 'alokasikan' or other keywords present in current copy.

#### Scenario: achievable hint contains current copy keywords

- **WHEN** `test_achievable_hint` runs to verify the hint for missing "achievable" criterion
- **THEN** the test should assert that the generated hint contains keywords from the current production copy (e.g., "target ini sudah pas", "satu sesi diskusi", "dipecah") rather than old keywords ("sumber", "cukup") that are no longer present

**Test location:** `tests/test_unit/test_intervention_and_goals.py::TestGenerateSocraticHint::test_achievable_hint`

**Source touchpoint:** `app/services/goal_validator.py:688-692` (achievable_hints list)

**Current production hint (example):** `"Apakah target ini sudah pas untuk satu sesi diskusi, atau perlu dipecah jadi beberapa langkah?"`

**Current test expectation (stale):** Checks for 'sumber' or 'cukup' - neither present in current copy

**Fix approach:** Read exact hint strings from goal_validator.py:688-692; update test to check for 'target ini sudah pas', 'sesi diskusi', 'dipecah' or other keywords present in current copy.

#### Scenario: multiple missing criteria uses first criterion hint

- **WHEN** `test_multiple_missing_uses_first` runs to verify behavior when multiple SMART criteria are missing
- **THEN** the test should verify that a hint for the first missing criterion is returned, and the hint should contain keywords from the current production copy for that criterion (subject to same keyword alignment as other tests)

**Test location:** `tests/test_unit/test_intervention_and_goals.py::TestGenerateSocraticHint::test_multiple_missing_uses_first`

**Source touchpoint:** `app/services/goal_validator.py:705-711` (primary_missing selection logic + hint generation)

**Current failure:** Test expects old time_bound keywords ('kapan', 'berencana') but current copy has different keywords

**Fix approach:** Update test to check for keywords present in current time_bound hints (or whichever criterion is tested as "first").

### Requirement: Async Dependencies Must Use AsyncMock

When production code uses async functions or coroutines, tests MUST mock those dependencies with `AsyncMock` (from `unittest.mock`) rather than plain `MagicMock`. Using plain `MagicMock` for an async dependency causes `TypeError: object MagicMock can't be used in 'await' expression` when the test attempts to await the mock.

#### Scenario: validate_goal_invalid_resets_streak uses AsyncMock for async dependency

- **WHEN** `test_validate_goal_invalid_resets_streak` runs and needs to mock an async dependency that was recently changed from sync to async
- **THEN** the test should use `AsyncMock()` instead of `MagicMock()` for the async dependency, allowing the test to successfully await the mock without raising `TypeError`

**Test location:** `tests/test_unit/test_orchestration_coverage.py::test_validate_goal_invalid_resets_streak`

**Source touchpoint:** (The production code that became async - exact location to be determined by inspecting test setup and identifying which mock needs to be AsyncMock)

**Current failure:** `TypeError: object MagicMock can't be used in 'await' expression`

**Fix approach:** 
1. Identify which mock in the test setup is being awaited (inspect test code and stack trace)
2. Replace `MagicMock()` with `AsyncMock()` for that dependency
3. Ensure any return values or side effects are also configured for async behavior if needed
4. Verify test passes after mock type change

**Root cause category:** Stale-test-vs-new-code (a production dependency that was sync became async, but the test mock was not updated)

### Requirement: Production Socratic Hint Copy Must Remain Unchanged

The production hint strings in `goal_validator.py` are assumed to be correct and MUST NOT be modified as part of this change. Only test assertions should be updated to match the current production copy.

#### Scenario: Production hints remain unchanged after test fixes

- **WHEN** test keyword assertions are updated to match current production copy
- **THEN** the production hint strings in `goal_validator.py` (lines 630-703) should remain exactly as they are, with no modifications to hint text, hint selection logic, or hint generation behavior

**Source touchpoint:** `app/services/goal_validator.py:609-711` (generate_socratic_hint method)

**Constraint:** Do NOT modify production hint copy unless investigation reveals semantic errors in the current copy.

