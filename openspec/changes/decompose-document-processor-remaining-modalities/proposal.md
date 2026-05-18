## Why

`decompose-document-processor-by-modality` (Complete) extracted `chunking.py` as a pure-function seam. However `document_processor.py` remains at **1347 LOC** with PDF/DOCX/PPTX text extraction, OCR, multimodal image processing, and storage all in one class. This change completes the modality extraction for `text_extraction.py` and `image_extraction.py`.

## What Changes

- Extract 2 per-modality modules into `app/services/document_processing/`:
  - `text_extraction.py` — `_process_pdf`, `_process_docx`, `_process_pptx`, `_process_text` + helpers (`_extract_images_from_docx`, `_process_extracted_images`) (~500 LOC)
  - `image_extraction.py` — `_process_image`, `_generate_image_caption`, `_run_ocr`, `_run_ocr_optimized`, `_initialize_ocr_engine`, `_run_page_ocr` (~250 LOC)
- `document_processor.py` becomes a thin orchestrator (~400 LOC) that imports and composes the 3 modules (chunking + text_extraction + image_extraction).
- Preserve public import: `from app.services.document_processor import DocumentProcessor` keeps working.
- `storage.py` deferred — `_store_chunks` is only ~40 LOC and tightly coupled to MongoDB logger; extraction has minimal value.

## Capabilities

### Modified Capabilities

- `ai-engine-service-maintainability` — completes the requirement that document processing is decomposed by modality with per-modality testability.

## Impact

- `app/services/document_processing/text_extraction.py` — new file.
- `app/services/document_processing/image_extraction.py` — new file.
- `app/services/document_processing/__init__.py` — updated re-exports.
- `app/services/document_processor.py` — becomes thin orchestrator.
- `tests/test_unit/test_document_processing_*.py` — new per-modality unit tests.
- `tests/test_unit/test_document_processor.py` — must pass without edits.
