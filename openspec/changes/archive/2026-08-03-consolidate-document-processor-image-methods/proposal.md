# Consolidate Image Processing Methods in DocumentProcessor

## Problem Statement

`DocumentProcessor` masih memiliki 6 method yang duplikat dengan module-level functions di `image_extraction.py`:

| Method di document_processor.py | Duplikat dengan |
|---|---|
| `_process_image` (L750-785) | `process_image` di image_extraction.py (L240-299) |
| `_generate_image_caption` (L787-834) | `generate_image_caption` (L170-237) |
| `_run_ocr` (L866) | OCR functions (L52-168) |
| `_run_paddle_ocr` (L869-897) | OCR functions |
| `_run_ocr_optimized` (L898-920) | OCR functions |
| `_run_page_ocr` (L921-942) | OCR functions |

## Proposed Solution

1. Refactor test mocks dari `self._method = AsyncMock(...)` ke `patch("app.services.document_processing.image_extraction.<func>", AsyncMock(...))`
2. Hapus 6 method duplikat dari `DocumentProcessor`
3. Update `DocumentProcessor.process_file` untuk panggil module-level functions langsung

## Scope

- `app/services/document_processor.py` — hapus 6 method (L750-942)
- Test files yang mock instance methods — refactor ke patch module functions
- `image_extraction.py` — pastikan API kompatibel sebagai single source of truth

## Out of Scope

- Logic changes di OCR/captioning behavior
- Performance optimizations
