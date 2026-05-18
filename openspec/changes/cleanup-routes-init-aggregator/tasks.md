## 1. Pre-flight

- [ ] 1.1 Run baseline: `pytest tests/ -q` — 2009 passing
- [ ] 1.2 Audit current `routes/__init__.py`: list all symbols and their categories
- [ ] 1.3 Grep all usage: `grep -rn "from app.api.routes import" app/ tests/ scripts/`

## 2. Create dependencies module

- [ ] 2.1 Buat `app/api/dependencies.py`
- [ ] 2.2 Re-export DI helpers (`get_vector_store`, `get_llm_service`, etc.)
- [ ] 2.3 Add `__all__` list

## 3. Update import sites

- [ ] 3.1 Update test files yang import dari `app.api.routes.*` → `app.api.dependencies.*`
- [ ] 3.2 Update internal route modules jika import dari aggregator
- [ ] 3.3 Update scripts/ jika ada

## 4. Slim down routes/__init__.py

- [ ] 4.1 Hapus DI helper re-exports
- [ ] 4.2 Hapus ingest functions/endpoints (move to documents.py kalau belum)
- [ ] 4.3 Final state: cuma router imports + includes

## 5. Verify

- [ ] 5.1 `pytest tests/ -q` — 2009 passing
- [ ] 5.2 `python -c "from app.api.routes import router; print(len(router.routes))"` — same count as before
- [ ] 5.3 `wc -l app/api/routes/__init__.py` — should be < 50 LOC
- [ ] 5.4 `openspec validate cleanup-routes-init-aggregator --strict`
