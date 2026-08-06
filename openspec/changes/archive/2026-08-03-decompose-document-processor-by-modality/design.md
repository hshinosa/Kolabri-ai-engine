## Context

`document_processor.py` has accumulated PDF + DOCX text extraction, OCR, multimodal image extraction (introduced in PHASE 4), chunking, and storage adaptation. The integration tests already cover the orchestration path, but the per-modality logic is hard to unit-test because every test must instantiate the full processor.

## Goals / Non-Goals

**Goals:**
- One module per modality with a narrow public surface.
- The orchestrator (formerly `DocumentProcessor`) becomes a thin composition layer.
- Per-modality unit tests can run without instantiating the full pipeline.
- Public import path `from app.services.document_processor import DocumentProcessor` keeps working.

**Non-Goals:**
- Replacing OCR engine.
- Changing chunking rules.
- Changing storage paths.
- Touching the multimodal Gemini Vision branch behavior.

## Decisions

### D1: Package, not module-rename
Use `app/services/document_processing/` to avoid colliding with the existing `document_processor.py` filename and to make per-modality imports explicit (e.g. `from app.services.document_processing import text_extraction`).

### D2: Orchestrator stays in `document_processor.py`
Keep `app/services/document_processor.py` as the entry point that imports from the new package. Existing call sites continue to work.

### D3: No DI framework
Each module exposes a small set of pure functions plus a class only where state is genuinely needed (e.g. an OCR client). No DI container is introduced.

### D4: Storage adapter is the only async-I/O concern in storage.py
Text and image extraction return Python data structures; only `storage.py` writes to disk. This keeps the modality boundaries clean.

## Risks / Trade-offs

- **Risk: hidden coupling between extraction and chunking** — Mitigation: extract first, chunk second; chunking only operates on text returned by the extractor.
- **Risk: existing tests under `tests/test_unit/test_document_processor*.py` import internal helpers** — Mitigation: keep those internal helpers re-exported from `document_processor.py` for backwards compatibility for one release cycle.

## Open Questions

- None.
