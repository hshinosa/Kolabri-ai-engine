# ocr-import-resilience Specification

## Purpose
TBD - created by archiving change ai-engine-fix-failing-tests. Update Purpose after archive.
## Requirements
### Requirement: OCR Import Tests Must Handle Broken Dependencies Gracefully

OCR functionality in the ai-engine is optional and depends on `paddle` and `paddleocr` packages. Tests that verify OCR availability MUST NOT trigger real `paddle` imports, which fail under Python 3.13 with paddle 3.0.0 due to circular import errors (`AttributeError: partially initialized module 'paddle' has no attribute 'tensor'/'pir'`). The production code already implements resilient import handling with try/except guards and `OCR_AVAILABLE` flags.

Tests MUST mock `paddle` imports or skip gracefully when paddle is broken in the environment, rather than allowing circular import errors to propagate into the test suite. This ensures test suite health is not dependent on specific paddle/Python version compatibility.

#### Scenario: document_processor OCR available when paddle and paddleocr present

- **WHEN** `test_document_processor_ocr_available_when_paddle_and_paddleocr_present` runs in an environment where paddle 3.0.0 + Python 3.13 causes circular import errors
- **THEN** the test should mock the paddle import at the module level (using `pytest.monkeypatch`, `unittest.mock.patch`, or similar) to simulate successful import, OR skip the test with `pytest.mark.skipif` when paddle import raises AttributeError, rather than failing with `AttributeError: partially initialized module 'paddle' has no attribute 'tensor'`

**Test location:** `tests/test_unit/test_coverage_to_100.py::test_document_processor_ocr_available_when_paddle_and_paddleocr_present`

**Source touchpoint:** `app/services/document_processor.py:54` (paddleocr import with try/except guard)

**Current failure:** Test attempts real paddle import → circular import → `AttributeError: partially initialized module 'paddle'... has no attribute 'tensor'`

**Fix approach:** Mock paddle at import level or skip when paddle is broken; do NOT attempt real import in test.

#### Scenario: document_processor OCR false when paddleocr without paddle

- **WHEN** `test_document_processor_ocr_false_when_paddleocr_without_paddle` runs and needs to verify OCR_AVAILABLE=False when paddle is missing
- **THEN** the test should mock the absence of paddle (e.g., make paddle import raise ImportError or AttributeError) without attempting real paddle import, ensuring the test verifies the production code's fallback behavior

**Test location:** `tests/test_unit/test_coverage_to_100.py::test_document_processor_ocr_false_when_paddleocr_without_paddle`

**Source touchpoint:** `app/services/document_processor.py:54` (paddleocr import with OCR_AVAILABLE flag)

**Current failure:** Test attempts real paddle import to verify negative case → circular import → `AttributeError`

**Fix approach:** Mock paddle import failure to test the OCR_AVAILABLE=False branch; reference existing branch-guard tests for mocking pattern.

#### Scenario: image_extraction OCR available when paddle present

- **WHEN** `test_image_extraction_ocr_available_when_paddle_present` runs to verify OCR availability in the image extraction module
- **THEN** the test should mock paddle import success without triggering real paddle circular import, allowing verification that `OCR_AVAILABLE=True` when dependencies are present

**Test location:** `tests/test_unit/test_coverage_to_100.py::test_image_extraction_ocr_available_when_paddle_present`

**Source touchpoint:** `app/services/document_processing/image_extraction.py` (paddle import with try/except guard)

**Current failure:** Real paddle import → circular import → `AttributeError: partially initialized module 'paddle'... has no attribute 'pir'`

**Fix approach:** Mock paddle at import level; verify OCR_AVAILABLE flag without real import.

#### Scenario: OCR import branch without paddle dependency

- **WHEN** `test_ocr_import_branch_without_paddle_dependency` runs to verify the code path when paddle is not available
- **THEN** the test should successfully mock paddle unavailability and verify the fallback behavior, without attempting real paddle import that would fail due to circular import

**Test location:** `tests/test_unit/test_document_processor_full.py::TestModuleLevelImports::test_ocr_import_branch_without_paddle_dependency`

**Source touchpoint:** `app/services/document_processor.py:54` (paddleocr import try/except)

**Current failure:** Test setup or assertion attempts real paddle import → circular import → `AttributeError`

**Fix approach:** Review how this test currently mocks paddle; ensure mocking happens before any real import attempt. This test should be a reference for the mocking pattern used by the other 4 tests.

#### Scenario: Additional paddle circular import variant

- **WHEN** any additional test in the paddle/OCR test cluster runs and encounters the circular import issue
- **THEN** the test should follow the same mocking or skip strategy as the other OCR import tests, ensuring no test attempts real paddle import under Python 3.13 + paddle 3.0.0

**Test location:** (One more test in the paddle circular import cluster - exact test name to be determined from full pytest output)

**Source touchpoint:** Same as above (`document_processor.py` or `image_extraction.py` paddle imports)

**Current failure:** Circular import → `AttributeError`

**Fix approach:** Apply same mocking pattern as tests above; investigate whether this is a duplicate of one of the 4 tests above or a separate test case.

### Requirement: Production OCR Import Guards Must Remain Unchanged

The production code's resilient import handling in `document_processor.py` and `image_extraction.py` is already correct and MUST NOT be modified. The try/except guards and `OCR_AVAILABLE`/`OCR_IMPORT_ERROR` flags correctly handle import failures at runtime.

#### Scenario: Production code handles paddle import failures gracefully

- **WHEN** production code runs in an environment where paddle/paddleocr imports fail
- **THEN** the existing try/except guards should catch the exception, set `OCR_AVAILABLE=False`, and continue without OCR functionality, exactly as currently implemented

**Source touchpoint:** `app/services/document_processor.py:54`, `app/services/document_processing/image_extraction.py`

**Constraint:** Do NOT modify production import guards; only fix tests.

