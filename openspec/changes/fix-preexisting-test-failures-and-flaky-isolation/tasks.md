## 1. Fix test_api_routes.py mock paths

- [x] 1.1 Patch `app.api.routes.health.get_vector_store` + mock all 5 deps for health check tests
- [x] 1.2 Fix degraded assertion (503 not 200)
- [x] 1.3 Patch `app.api.routes.chat.get_rag_pipeline` for ask tests
- [x] 1.4 Patch `app.api.routes.analytics.get_engagement_analyzer` for engagement test
- [x] 1.5 Patch `app.api.routes.analytics.get_orchestrator` for dashboard tests

## 2. Fix grounding verifier sync mock

- [x] 2.1 Add `_compute_similarity` mock to `test_grounding_verifier_async.py` (3 tests)
- [x] 2.2 Add `_compute_similarity` mock to `test_rag_accuracy.py` (1 test)

## 3. Fix coverage_gaps_extra mock method name

- [x] 3.1 Mock `verify_grounding_async` (not `verify_grounding`) with AsyncMock (2 tests)

## 4. Fix flaky PIL Image isolation

- [x] 4.1 Update `_patch_pil_image` fixture to patch both `document_processor.Image` and `text_extraction.Image`
- [x] 4.2 Read `sys.modules["PIL.Image"]` at fixture time
- [x] 4.3 Set `ms.MAX_IMAGES_PER_PAGE = 3` in `test_pdf_vision_multiple_images_capped`

## 5. Verify

- [x] 5.1 `pytest tests/test_unit/ tests/test_integration/ -q` — 2009 passed, 0 failed
