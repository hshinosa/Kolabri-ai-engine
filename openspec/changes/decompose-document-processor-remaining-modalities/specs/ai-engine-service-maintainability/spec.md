## MODIFIED Requirements

### Requirement: Document processing is decomposed by modality

The AI engine MUST partition document-processing logic into modality-specific modules under `app/services/document_processing/`. `decompose-document-processor-by-modality` extracted `chunking.py`; this change extracts `text_extraction.py` and `image_extraction.py`.

#### Scenario: Text extraction module contains PDF/DOCX/PPTX/text processors

- **WHEN** a developer needs to test or modify PDF, DOCX, PPTX, or plain text extraction
- **THEN** the logic MUST live in `app/services/document_processing/text_extraction.py` and expose `process_pdf()`, `process_docx()`, `process_pptx()`, `process_text()` as module-level async functions

#### Scenario: Image extraction module contains image/OCR/caption processors

- **WHEN** a developer needs to test or modify image processing, OCR, or caption generation
- **THEN** the logic MUST live in `app/services/document_processing/image_extraction.py` and expose `process_image()`, `generate_image_caption()`, `run_ocr()`, `run_ocr_optimized()`, `initialize_ocr_engine()` as module-level functions

#### Scenario: DocumentProcessor becomes thin orchestrator

- **WHEN** `DocumentProcessor.process_file()` is called
- **THEN** it MUST delegate to the appropriate per-modality function from `text_extraction` or `image_extraction` module, remaining under 400 LOC

#### Scenario: Per-modality unit tests exist

- **WHEN** text_extraction or image_extraction modules are changed
- **THEN** per-modality unit tests MUST pass without instantiating the full `DocumentProcessor`
