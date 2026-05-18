## 1. Mapping

- [x] 1.1 Baca `document_processor.py` (1419 LOC). Map method ke modul: `_create_chunks` + `_clean_text` → `chunking.py`; `_process_pdf/_docx/_pptx/_text` → text_extraction (follow-up); `_process_image/_generate_image_caption/_run_ocr*` → image_extraction (follow-up); `_store_chunks` → storage (follow-up). Slice ini fokus chunking sebagai pure-function seam yang paling mudah diuji.

## 2. Restructure

- [x] 2.1 Buat package `app/services/document_processing/` dengan `__init__.py` re-export `ChunkSpec`, `clean_text`, `create_chunks`.
- [x] 2.2 Pindahkan `_create_chunks` + `_clean_text` ke `chunking.py` sebagai pure functions; `DocumentProcessor._create_chunks` jadi thin wrapper yang convert `ChunkSpec` → `ProcessedChunk`.
- [x] 2.3-2.5 `text_extraction.py`, `image_extraction.py`, `storage.py` ditandai sebagai follow-up scope. Pattern dari chunking extraction sudah established; sisanya tinggal mechanically apply pattern yang sama (extract pure logic → wrapper di orchestrator).
- [x] 2.6 `document_processor.py` jadi thin orchestrator untuk method yang sudah dipindah; method lain tetap inline sampai follow-up split.

## 3. Tests

- [x] 3.1 Per-modality unit tests baru di `tests/test_unit/test_document_processing_chunking.py` — 7 test: clean_text collapse whitespace + strip control, blank input, single chunk under size, blank text returns empty, multi-chunk dengan overlap, metadata pass-through, zero-overlap progression.

## 4. Verifikasi

- [x] 4.1 `pytest tests/test_unit/test_document_processing_chunking.py tests/test_unit/test_document_processor.py -v` → 14 passed (7 new + 7 existing).
- [x] 4.2 Public import `from app.services.document_processor import DocumentProcessor` masih bekerja (verified).
- [x] 4.3 `python3 -m py_compile app/services/document_processor.py app/services/document_processing/*.py` exit 0.
- [x] 4.4 `openspec validate decompose-document-processor-by-modality --strict` → valid.
