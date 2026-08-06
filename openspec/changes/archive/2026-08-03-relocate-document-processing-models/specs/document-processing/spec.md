# Document Processing Models Relocation

## ADDED Requirements

### Requirement: Self-contained document_processing package

The `app/services/document_processing/` package SHALL be self-contained — it MUST NOT import from its parent `document_processor` module.

#### Scenario: Extracted module imports models

- Given `text_extraction.py` needs `ProcessedDocument` and `ProcessedChunk`
- When the file declares its imports
- Then it MUST use `from app.services.document_processing.models import ProcessedDocument, ProcessedChunk`
- And MUST NOT use `from app.services.document_processor import ProcessedDocument`

#### Scenario: No circular import workarounds

- Given any module inside `app/services/document_processing/`
- When it needs to use `ProcessedDocument` or `ProcessedChunk`
- Then the import MUST be at module top-level (not inside functions)
- And there MUST NOT be inline imports used to avoid circular dependency
