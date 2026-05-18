## 1. Pre-flight

- [ ] 1.1 Run baseline: `pytest tests/ -q` — record 2009 passed
- [ ] 1.2 Document all test files yang mock `self._run_paddle_ocr`, `self._generate_image_caption`, `self._process_image`, `self._run_ocr*`

## 2. Refactor test mocks

- [ ] 2.1 `test_document_processor_full.py` — migrate semua instance method mock ke module-level patch
- [ ] 2.2 Update `proc_ocr` and `proc_vision` fixtures jika perlu
- [ ] 2.3 Run tests setelah setiap file refactor — pastikan 2009 passing tetap

## 3. Remove duplicate methods from DocumentProcessor

- [ ] 3.1 Delete `_process_image` (L750-785) — update call sites untuk pakai `image_extraction.process_image`
- [ ] 3.2 Delete `_generate_image_caption` (L787-834)
- [ ] 3.3 Delete `_run_ocr`, `_run_paddle_ocr`, `_run_ocr_optimized`, `_run_page_ocr` (L866-942)
- [ ] 3.4 Verify `document_processor.py` reduced from 1023 → ~700 LOC

## 4. Verify

- [ ] 4.1 `pytest tests/ -q` — 2009 passing
- [ ] 4.2 `openspec validate consolidate-document-processor-image-methods --strict`
- [ ] 4.3 No grep results for `_process_image|_generate_image_caption|_run_paddle_ocr|_run_ocr_optimized|_run_page_ocr` di `document_processor.py`
