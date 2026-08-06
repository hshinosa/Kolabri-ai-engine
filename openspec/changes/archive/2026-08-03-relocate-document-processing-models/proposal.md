# Relocate Document Processing Models to Dedicated Module

## Problem Statement

`text_extraction.py` dan `image_extraction.py` melakukan **reverse imports** dari parent `document_processor`:

```python
# 8 occurrences across 2 files
from app.services.document_processor import ProcessedDocument, ProcessedChunk
```

Ini menciptakan abstraction leak — package `document_processing` tidak self-contained, dan ada risiko circular dependency.

## Proposed Solution

Buat `app/services/document_processing/models.py` yang berisi:
- `ProcessedChunk` dataclass
- `ProcessedDocument` dataclass

Pindahkan kedua dataclass dari `document_processor.py` ke `models.py`. Update semua import sites.

## Scope

- Buat `app/services/document_processing/models.py` (baru)
- Update `text_extraction.py` — 4 inline imports
- Update `image_extraction.py` — 1 inline import
- Update `document_processor.py` — pindahkan dataclass + import dari `models.py` (atau re-export untuk backward compat)
- Update `chunking.py` jika perlu

## Out of Scope

- Schema changes pada dataclass fields
- Public API changes
