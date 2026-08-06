# Design

## Root Causes

### 1. Stale mock paths (12 failures)

After S3 route extraction, endpoints moved from `app.api.routes._legacy` to submodules (`chat.py`, `analytics.py`, `health.py`). Tests still patched at `app.api.routes.*` level which no longer re-exports those functions.

**Fix:** Patch at correct submodule path (e.g., `app.api.routes.chat.get_rag_pipeline`).

### 2. Missing sync mock (3 failures)

`verify_grounding_async` calls both `_compute_similarity_async` (mocked) and `_compute_similarity` (NOT mocked). The sync version returns garbage from MagicMock, causing hybrid_score calculation to fail.

**Fix:** Add `patch.object(verifier, "_compute_similarity", return_value=X)` alongside async mock.

### 3. PIL Image mock isolation (3 flaky)

`test_api_routes.py` overrides `sys.modules['PIL'] = MagicMock()` at module level. `text_extraction.py` imports `from PIL import Image` directly — gets MagicMock instead of `_FakeImageModule`. The `_patch_pil_image` fixture only patched `document_processor.Image`.

**Fix:** Fixture now patches both `document_processor.Image` and `text_extraction.Image`, reads from `sys.modules` at fixture time.
