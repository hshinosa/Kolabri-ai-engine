## 1. Pre-flight

- [x] 1.1 Run baseline: `pytest tests/ -q` — 2009 passing
- [x] 1.2 Audit current `routes/__init__.py`: list all symbols and their categories
- [x] 1.3 Grep all usage: `grep -rn "from app.api.routes import" app/ tests/ scripts/`

## 2. Create dependencies module

- [x] 2.1 Buat `app/api/dependencies.py`
- [x] 2.2 Re-export DI helpers (`get_vector_store`, `get_llm_service`, etc.)
- [x] 2.3 Add `__all__` list

## 3. Update import sites

- [x] 3.1 Update test files yang import dari `app.api.routes.*` → `app.api.dependencies.*`
- [x] 3.2 Update internal route modules jika import dari aggregator
- [x] 3.3 Update scripts/ jika ada

## 4. Slim down routes/__init__.py

- [x] 4.1 Hapus DI helper re-exports
- [x] 4.2 Hapus ingest functions/endpoints (move to documents.py kalau belum)
- [x] 4.3 Final state: cuma router imports + includes

## 5. Verify

- [x] 5.1 `pytest tests/ -q` — 2009 passing
- [x] 5.2 `python -c "from app.api.routes import router; print(len(router.routes))"` — same count as before
- [x] 5.3 `wc -l app/api/routes/__init__.py` — should be < 50 LOC
- [x] 5.4 `openspec validate cleanup-routes-init-aggregator --strict`
