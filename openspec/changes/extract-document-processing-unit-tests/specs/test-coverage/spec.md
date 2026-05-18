# Document Processing Unit Test Coverage

## ADDED Requirements

### Requirement: Module-level functions MUST have direct unit tests

Module-level functions in `app/services/document_processing/` SHALL have unit tests that import and invoke them directly, without going through `DocumentProcessor`.

#### Scenario: Direct test of process_pdf

- Given `text_extraction.process_pdf` is a module-level async function
- When unit testing this function
- Then the test MUST import it as `from app.services.document_processing.text_extraction import process_pdf`
- And invoke it with explicit parameters (no `DocumentProcessor` instance)
- And mock dependencies via injected parameters (`_fitz`, `caption_fn`, etc.)

#### Scenario: Coverage requirement

- Given the modules `text_extraction.py` and `image_extraction.py`
- When the test suite runs with coverage
- Then per-module line coverage MUST be at least 90%
- And coverage MUST be attributable to direct module tests, not just integration via `DocumentProcessor`
