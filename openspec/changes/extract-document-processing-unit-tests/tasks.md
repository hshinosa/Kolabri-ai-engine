## 1. Pre-flight

- [ ] 1.1 Run baseline coverage: `pytest tests/ --cov=app/services/document_processing --no-cov-on-fail` — record per-module coverage
- [ ] 1.2 Identify untested module functions

## 2. Create text_extraction tests

- [ ] 2.1 Buat `tests/test_unit/test_document_processing_text_extraction.py`
- [ ] 2.2 Test `process_pdf` — happy path, OCR fallback, vision captions, image cap
- [ ] 2.3 Test `process_docx` — text extraction, table handling, image extraction
- [ ] 2.4 Test `process_pptx` — slide text extraction
- [ ] 2.5 Test `process_text` — markdown, plain text
- [ ] 2.6 Test `_extract_images_from_docx` — happy, corrupt zip, corrupt image
- [ ] 2.7 Run: target coverage > 90% untuk `text_extraction.py`

## 3. Create image_extraction tests

- [ ] 3.1 Buat `tests/test_unit/test_document_processing_image_extraction.py`
- [ ] 3.2 Test `process_image` — happy, no vision, OCR-only
- [ ] 3.3 Test `generate_image_caption` — success, empty response, error handling
- [ ] 3.4 Test `run_paddle_ocr` — success, no OCR engine, multiple results
- [ ] 3.5 Test `run_ocr_optimized` — page-based OCR
- [ ] 3.6 Test `initialize_ocr_engine` — disabled, enabled
- [ ] 3.7 Run: target coverage > 90% untuk `image_extraction.py`

## 4. Verify

- [ ] 4.1 `pytest tests/ -q` — all tests passing
- [ ] 4.2 Check coverage report — module-level coverage > 90%
- [ ] 4.3 No regression di existing test count (2009+)
- [ ] 4.4 `openspec validate extract-document-processing-unit-tests --strict`
