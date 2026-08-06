## Why

`app/services/document_processor.py` is 1,419 LOC — the single largest service file. It mixes PDF text extraction, DOCX extraction, OCR, multimodal image extraction, chunking, and storage handoff. Every modality is tested through one big class, and a failure in one path can mask issues in the others. Slice S5 in `improve-ai-engine-testability-and-maintainability` § G calls for decomposition by modality.

## What Changes

- Introduce `app/services/document_processing/` package with one module per concern:
  - `text_extraction.py` — PDF, DOCX, plain text extraction.
  - `image_extraction.py` — multimodal/image extraction (PHASE 4 multimodal RAG).
  - `chunking.py` — chunking rules (`CHUNK_SIZE`, `CHUNK_OVERLAP`).
  - `storage.py` — image storage adapter (writes under `STORAGE_IMAGE_DIR`).
- Replace `document_processor.py` with a thin orchestrator that composes the four modules.
- Preserve existing public API: anything importing `DocumentProcessor` from `app.services.document_processor` keeps working.

## Capabilities

### Modified Capabilities

- `ai-engine-service-maintainability` — adds the requirement that document processing is decomposed by modality with per-modality testability.

## Impact

- `app/services/document_processing/{__init__.py, text_extraction.py, image_extraction.py, chunking.py, storage.py}` — new files.
- `app/services/document_processor.py` — becomes a thin orchestrator that imports and composes the package modules.
- `tests/test_unit/test_document_processor*.py` — must continue to pass; new per-modality unit tests added.
