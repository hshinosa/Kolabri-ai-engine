## 1. Pre-flight

- [x] 1.1 Run baseline coverage: `pytest tests/ --cov=app/services/document_processing --no-cov-on-fail` — record per-module coverage
- [x] 1.2 Identify untested module functions

## 2. Create text_extraction tests

- [x] 2.1 Buat `tests/test_unit/test_document_processing_text_extraction.py`
- [x] 2.2 Test `process_pdf` — happy path, OCR fallback, vision captions, image cap
- [x] 2.3 Test `process_docx` — text extraction, table handling, image extraction
- [x] 2.4 Test `process_pptx` — slide text extraction
- [x] 2.5 Test `process_text` — markdown, plain text
- [x] 2.6 Test `_extract_images_from_docx` — happy, corrupt zip, corrupt image
- [x] 2.7 Run: target coverage > 90% untuk `text_extraction.py`

## 3. Create image_extraction tests

- [x] 3.1 Buat `tests/test_unit/test_document_processing_image_extraction.py`
- [x] 3.2 Test `process_image` — happy, no vision, OCR-only
- [x] 3.3 Test `generate_image_caption` — success, empty response, error handling
- [x] 3.4 Test `run_paddle_ocr` — success, no OCR engine, multiple results
- [x] 3.5 Test `run_ocr_optimized` — page-based OCR
- [x] 3.6 Test `initialize_ocr_engine` — disabled, enabled
- [x] 3.7 Run: target coverage > 90% untuk `image_extraction.py`

## 4. Verify

- [x] 4.1 `pytest tests/ -q` — all tests passing
- [x] 4.2 Check coverage report — module-level coverage > 90%
- [x] 4.3 No regression di existing test count (2009+)
- [x] 4.4 `openspec validate extract-document-processing-unit-tests --strict`
