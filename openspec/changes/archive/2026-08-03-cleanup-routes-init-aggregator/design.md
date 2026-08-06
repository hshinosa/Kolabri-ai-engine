# Design

## Current State Audit

`app/api/routes/__init__.py` contains:

1. **Router imports + includes** (correct):
   - `from .documents import router as _documents_router`
   - `router.include_router(_documents_router)`

2. **DI helper re-exports** (misplaced):
   ```python
   from app.services.vector_store import get_vector_store
   from app.services.llm import get_llm_service
   from app.services.rag import get_rag_pipeline
   # ...
   ```

3. **Ingest functions/endpoints** (misplaced — should be in documents.py):
   - `_process_pdf_background` (or similar)
   - `/api/ingest/legacy` (if any)

## Target State

### Option A: Dedicated dependencies module

Buat `app/api/dependencies.py`:
```python
"""Dependency injection helpers for route modules."""
from app.services.vector_store import get_vector_store
from app.services.llm import get_llm_service
# ...

__all__ = ["get_vector_store", "get_llm_service", ...]
```

Route modules import dari `app.api.dependencies` instead of `app.api.routes`.

### Option B: Keep DI helpers in routes/__init__.py for backward compat

Tetap re-export di `__init__.py` dengan `__all__` explicit, tapi pindahkan ingest functions ke `documents.py`.

## Recommendation

Option A. Lebih clean architecture, dan refactor sites yang import dari `app.api.routes.get_vector_store` (cek dengan grep).

## Migration Steps

1. Identify all usages: `grep -rn "from app.api.routes import" app/ tests/`
2. Buat `app/api/dependencies.py` dengan re-exports
3. Update import sites
4. Hapus re-exports dari `__init__.py`
5. Hapus ingest functions dari `__init__.py` (move to documents.py kalau belum)

## Backward Compat Risk

Kalau external code (e.g., scripts/) import `from app.api.routes import get_vector_store`, akan break. Mitigation:
- Grep dulu semua import sites
- Update inline
- Atau biarkan re-exports tetap ada dengan deprecation warning
