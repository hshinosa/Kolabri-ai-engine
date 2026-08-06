# Cleanup routes/__init__.py to Pure Aggregator

## Problem Statement

`app/api/routes/__init__.py` saat ini bukan pure aggregator. Masih berisi:
- 8 DI helper re-exports (`get_vector_store`, `get_llm_service`, `get_orchestrator`, dll.)
- 2 ingest background functions
- 2 ingest endpoints

Ideal aggregator harusnya cuma:
- Import per-capability routers
- `router.include_router(...)` calls
- Public symbol re-exports untuk backward compat (kalau ada)

## Proposed Solution

1. Pindahkan DI helpers ke `app/api/dependencies.py` (kalau belum ada) atau ke modul sendiri
2. Pindahkan ingest endpoints + background functions yang masih di `__init__.py` ke `documents.py` (atau confirm sudah di sana, tinggal hapus duplicate di __init__)
3. `__init__.py` final state:
   ```python
   from fastapi import APIRouter
   from .documents import router as _documents_router
   from .chat import router as _chat_router
   # ... 9 imports

   router = APIRouter()
   router.include_router(_documents_router, tags=["Documents"])
   # ... 9 includes
   ```

## Scope

- `app/api/routes/__init__.py` — bersihkan jadi pure aggregator
- `app/api/dependencies.py` (mungkin baru) — house DI helpers
- Update import sites yang reference `from app.api.routes import get_vector_store` dst.

## Out of Scope

- Renaming endpoints
- Auth/middleware refactoring
