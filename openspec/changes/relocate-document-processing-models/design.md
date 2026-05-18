# Design

## Current State

`ProcessedDocument` dan `ProcessedChunk` di-define di `document_processor.py`. Extracted modules (`text_extraction.py`, `image_extraction.py`) butuh dataclass ini, jadi mereka import balik:

```python
# text_extraction.py:67, 185, 268, 345 (inline imports inside functions to avoid circular)
from app.services.document_processor import ProcessedDocument, ProcessedChunk
```

Pattern inline-import ini **smell** — indikator circular dependency yang di-workaround.

## Target State

```
app/services/document_processing/
├── __init__.py        # re-export public API
├── models.py          # ProcessedDocument, ProcessedChunk (NEW)
├── chunking.py        # depends on models
├── text_extraction.py # depends on models (clean import)
└── image_extraction.py # depends on models (clean import)
```

`document_processor.py` jadi pure orchestrator — import dari `document_processing.models` seperti consumer biasa.

## Migration Steps

1. Buat `models.py` dengan dataclass yang persis sama
2. Update semua 8 inline imports → top-level imports dari `.models`
3. Hapus dataclass dari `document_processor.py`, tambah top-level import `from app.services.document_processing.models import ProcessedDocument, ProcessedChunk`
4. Untuk backward compat: re-export dari `document_processor` module via `__all__`

## Backward Compat

Code lain mungkin import via `from app.services.document_processor import ProcessedDocument`. Tetap support via re-export di `document_processor.py`.
