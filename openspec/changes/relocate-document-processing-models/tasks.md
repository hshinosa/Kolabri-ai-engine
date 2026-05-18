## 1. Pre-flight

- [x] 1.1 Run baseline: `pytest tests/ -q` — 2009 passing
- [x] 1.2 Grep semua import `ProcessedDocument` dan `ProcessedChunk`: `grep -rn "ProcessedDocument\|ProcessedChunk" app/ tests/`

## 2. Create models.py

- [x] 2.1 Buat `app/services/document_processing/models.py`
- [x] 2.2 Define `ProcessedChunk` dataclass (copy from `document_processor.py`)
- [x] 2.3 Define `ProcessedDocument` dataclass
- [x] 2.4 `python -m py_compile app/services/document_processing/models.py` — exit 0

## 3. Update extracted modules

- [x] 3.1 `text_extraction.py` — replace 4 inline imports with top-level `from app.services.document_processing.models import ProcessedDocument, ProcessedChunk`
- [x] 3.2 `image_extraction.py` — replace 1 inline import
- [x] 3.3 Run tests setelah setiap file edit

## 4. Update document_processor.py

- [x] 4.1 Hapus `@dataclass` definitions untuk `ProcessedDocument` dan `ProcessedChunk`
- [x] 4.2 Add top-level import dari `.document_processing.models`
- [x] 4.3 Add `__all__` untuk re-export backward compat
- [x] 4.4 Verify `document_processor.py` masih syntactically valid

## 5. Update __init__.py re-exports

- [x] 5.1 `app/services/document_processing/__init__.py` — add `from .models import ProcessedDocument, ProcessedChunk`

## 6. Verify

- [x] 6.1 `pytest tests/ -q` — 2009 passing
- [x] 6.2 `openspec validate relocate-document-processing-models --strict`
- [x] 6.3 No more `from app.services.document_processor import ProcessedDocument` di `document_processing/` package
