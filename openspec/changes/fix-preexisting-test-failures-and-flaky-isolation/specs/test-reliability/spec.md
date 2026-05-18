# Test Fix Specifications

## MODIFIED Requirements

### Requirement: Mock path accuracy

All test mock patches SHALL target the actual import location in the module under test, not re-exported aliases.

#### Scenario: Health check test mocks

- Given test `test_health_check_healthy`
- When patching `get_vector_store`
- Then patch target must be `app.api.routes.health.get_vector_store` (not `app.api.routes.get_vector_store`)
- And all 5 dependencies must be mocked (vector_store, llm, mongo, redis, circuit_breaker)

#### Scenario: Degraded health returns 503

- Given test `test_health_check_degraded`
- When health check detects degraded services
- Then response status must be 503 (not 200)

### Requirement: Sync+async mock alignment

Tests that mock `_compute_similarity_async` MUST also mock `_compute_similarity` (sync) when the code under test calls both.

#### Scenario: Grounding verifier hybrid score

- Given `verify_grounding_async` computes `hybrid_score = 0.7 * embedding_sim + 0.3 * keyword_sim`
- When test mocks `_compute_similarity_async` but not `_compute_similarity`
- Then sync version returns garbage from MagicMock
- And hybrid_score calculation fails

### Requirement: PIL Image mock isolation

The `_patch_pil_image` autouse fixture MUST patch Image in all modules that import it, not just `document_processor`.

#### Scenario: text_extraction uses PIL directly

- Given `text_extraction.py` imports `from PIL import Image`
- When `test_api_routes.py` overrides `sys.modules['PIL'] = MagicMock()`
- Then `text_extraction.Image` becomes MagicMock
- And `_extract_images_from_docx` cannot detect corrupt images
