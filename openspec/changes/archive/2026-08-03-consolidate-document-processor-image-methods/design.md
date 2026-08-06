# Design

## Root Cause

S5 partial extraction kept 6 OCR/image methods inline di `DocumentProcessor` untuk backward compat dengan test yang mock `self._run_paddle_ocr` dst. Ini menciptakan two source of truth: bug fix di satu tempat tidak otomatis fix di tempat lain.

## Approach

### Test Mock Strategy Migration

Lama (instance-level):
```python
proc._run_paddle_ocr = MagicMock(return_value="text")
```

Baru (module-level):
```python
with patch("app.services.document_processing.image_extraction.run_paddle_ocr", return_value="text"):
    ...
```

### Method Removal Plan

Hapus dari `DocumentProcessor`:
- `_process_image` → call sites pakai `image_extraction.process_image(...)`
- `_generate_image_caption` → `image_extraction.generate_image_caption(image, self._vision_model)`
- `_run_ocr`, `_run_paddle_ocr`, `_run_ocr_optimized`, `_run_page_ocr` → semua module-level

### Backward Compat

Tidak ada public API change. `DocumentProcessor.process_file` tetap interface sama. Cuma internal delegation yang berubah.
