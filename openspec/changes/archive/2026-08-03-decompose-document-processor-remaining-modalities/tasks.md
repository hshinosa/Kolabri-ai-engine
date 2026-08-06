## 1. Pre-flight

- [x] 1.1 Run baseline: `cd /Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine && python -m pytest tests/ -x -q` — record test count. All must pass.
- [x] 1.2 Read `document_processor.py` fully. Document method signatures and dependencies.
- [x] 1.3 Verify existing chunking extraction: `python -c "from app.services.document_processing import clean_text, create_chunks, ChunkSpec"` works.

## 2. Extract text_extraction.py

- [x] 2.1 Create `app/services/document_processing/text_extraction.py`.
- [x] 2.2 Move `_process_pdf` (L675) as `async def process_pdf(...)`. Parameters: `content`, `filename`, `document_id`, `metadata`, `file_path`, `ocr_available`, `vision_available`, `min_text_length_for_ocr`, `max_images_per_page`, `ocr_fn`, `caption_fn`, `create_chunks_fn`. Returns `ProcessedDocument`.
- [x] 2.3 Move `_process_docx` (L802) as `async def process_docx(...)`. Similar parameter pattern.
- [x] 2.4 Move `_process_pptx` (L873) as `async def process_pptx(...)`.
- [x] 2.5 Move `_process_text` (L948) as `async def process_text(...)`.
- [x] 2.6 Move `_extract_images_from_docx` (L1114) as internal helper `def _extract_images_from_docx(...)`.
- [x] 2.7 Move `_process_extracted_images` (L1130) as `async def process_extracted_images(...)`.
- [x] 2.8 Imports: `fitz`, `Image`, `io`, `zipfile`, `tempfile`, `os`, `gc`, `ProcessedDocument`, `ProcessedChunk` from models, `create_chunks` from chunking module, `get_logger`.
- [x] 2.9 `python -m py_compile app/services/document_processing/text_extraction.py` — exit 0.

## 3. Extract image_extraction.py

- [x] 3.1 Create `app/services/document_processing/image_extraction.py`.
- [x] 3.2 Move `_process_image` (L989) as `async def process_image(...)`. Parameters: `content`, `filename`, `document_id`, `metadata`, `vision_available`, `caption_fn`, `create_chunks_fn`. Returns `ProcessedDocument`.
- [x] 3.3 Move `_generate_image_caption` (L1047) as `async def generate_image_caption(image, llm_client) -> str`. Receives LLM client as parameter instead of `self.llm`.
- [x] 3.4 Move `_run_ocr` (L1162) as `async def run_ocr(image, ocr_engine) -> str`.
- [x] 3.5 Move `_run_ocr_optimized` (L1202) as `async def run_ocr_optimized(image, ocr_engine) -> str`.
- [x] 3.6 Move `_initialize_ocr_engine` (L1144) as `def initialize_ocr_engine(ocr_settings) -> Optional[PaddleOCR]`.
- [x] 3.7 Move `_run_page_ocr` (if exists) as internal helper.
- [x] 3.8 Imports: `Image`, `io`, `base64`, `PaddleOCR`, `OCR_AVAILABLE`, settings, `get_logger`.
- [x] 3.9 `python -m py_compile app/services/document_processing/image_extraction.py` — exit 0.

## 4. Update __init__.py re-exports

- [x] 4.1 Update `app/services/document_processing/__init__.py` to re-export from all 3 modules:
  - chunking: `ChunkSpec`, `clean_text`, `create_chunks`
  - text_extraction: `process_pdf`, `process_docx`, `process_pptx`, `process_text`
  - image_extraction: `process_image`, `generate_image_caption`, `run_ocr`, `run_ocr_optimized`, `initialize_ocr_engine`

## 5. Refactor DocumentProcessor as thin orchestrator

- [x] 5.1 In `document_processor.py`, import from `app.services.document_processing.text_extraction` and `app.services.document_processing.image_extraction`.
- [x] 5.2 Replace `_process_pdf` body with delegation to `text_extraction.process_pdf(...)`, passing self's settings/clients as params.
- [x] 5.3 Replace `_process_docx` body with delegation to `text_extraction.process_docx(...)`.
- [x] 5.4 Replace `_process_pptx` body with delegation to `text_extraction.process_pptx(...)`.
- [x] 5.5 Replace `_process_text` body with delegation to `text_extraction.process_text(...)`.
- [x] 5.6 Replace `_process_image` body with delegation to `image_extraction.process_image(...)`.
- [x] 5.7 Replace `_generate_image_caption` body with delegation to `image_extraction.generate_image_caption(self.llm, ...)`.
- [x] 5.8 Replace `_run_ocr` / `_run_ocr_optimized` body with delegation to `image_extraction.*`.
- [x] 5.9 Replace `_initialize_ocr_engine` body with delegation to `image_extraction.initialize_ocr_engine(...)`.
- [x] 5.10 Keep `_create_chunks` and `_store_chunks` inline (already extracted to chunking.py for create_chunks, store_chunks stays).
- [x] 5.11 Verify `document_processor.py` < 400 LOC after refactor.
- [x] 5.12 `python -m py_compile app/services/document_processor.py` — exit 0.

## 6. Unit tests for text_extraction

- [x] 6.1 Create `tests/test_unit/test_document_processing_text_extraction.py`.
- [x] 6.2 Test `process_text`: UTF-8 input → chunks created.
- [x] 6.3 Test `process_text`: invalid encoding → raises ValueError.
- [x] 6.4 Test `process_pdf` (mock fitz): text extraction + chunking called.
- [x] 6.5 Test `process_docx` (mock docx): text extraction + chunking called.
- [x] 6.6 `python -m pytest tests/test_unit/test_document_processing_text_extraction.py -v` — all pass.

## 7. Unit tests for image_extraction

- [x] 7.1 Create `tests/test_unit/test_document_processing_image_extraction.py`.
- [x] 7.2 Test `process_image`: vision unavailable → returns empty ProcessedDocument.
- [x] 7.3 Test `generate_image_caption` (mock LLM): returns caption string.
- [x] 7.4 Test `run_ocr` (mock PaddleOCR): returns text.
- [x] 7.5 Test `initialize_ocr_engine`: OCR unavailable → returns None.
- [x] 7.6 `python -m pytest tests/test_unit/test_document_processing_image_extraction.py -v` — all pass.

## 8. Verify

- [x] 8.1 `python -m pytest tests/ -x -q` — all tests pass (existing + new).
- [x] 8.2 `python -m py_compile app/services/document_processor.py app/services/document_processing/*.py` — exit 0.
- [x] 8.3 `python -c "from app.services.document_processor import DocumentProcessor"` — works.
- [x] 8.4 `wc -l app/services/document_processor.py` — < 400 LOC.
- [x] 8.5 `openspec validate decompose-document-processor-remaining-modalities --strict` — valid.
