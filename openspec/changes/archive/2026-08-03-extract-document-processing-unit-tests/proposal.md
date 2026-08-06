# Extract Unit Tests for Document Processing Modules

## Problem Statement

Setelah S5 extraction, modules `text_extraction.py` (378 LOC) dan `image_extraction.py` (299 LOC) **tidak punya unit test sendiri**. Coverage masih via `test_document_processor_full.py` yang test through `DocumentProcessor` instance.

Konsekuensi:
- Test masih coupled ke `DocumentProcessor` lifecycle
- Module-level functions tidak di-test sebagai pure functions
- Refactor `DocumentProcessor` (e.g., consolidate-document-processor-image-methods) bisa break test extracted modules walau function-nya correct
- Coverage report misleading — coverage `image_extraction.py` lewat instance method, bukan langsung

## Proposed Solution

Buat:
- `tests/test_unit/test_document_processing_text_extraction.py`
- `tests/test_unit/test_document_processing_image_extraction.py`

Yang test module-level functions secara langsung dengan dependency injection (`_fitz`, `_DocxDocument`, `caption_fn`, dll.) tanpa instantiate `DocumentProcessor`.

## Scope

- `tests/test_unit/test_document_processing_text_extraction.py` (baru) — test `process_pdf`, `process_docx`, `process_pptx`, `process_text`
- `tests/test_unit/test_document_processing_image_extraction.py` (baru) — test `process_image`, `generate_image_caption`, `run_paddle_ocr`, `run_ocr_optimized`
- Existing `test_document_processor_full.py` — biarkan untuk integration-style testing through `DocumentProcessor`

## Out of Scope

- Removing `test_document_processor_full.py` (still useful as integration test)
- Refactoring extraction module APIs
