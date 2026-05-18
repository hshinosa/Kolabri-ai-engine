## ADDED Requirements

### Requirement: Document processing is decomposed by modality

The AI engine MUST partition document-processing logic into modality-specific modules under `app/services/document_processing/`, where each module owns one concern.

#### Scenario: Text extraction is its own module

- **WHEN** a developer needs to test or modify PDF/DOCX/plain-text extraction
- **THEN** the logic MUST live in `app/services/document_processing/text_extraction.py` and be callable without instantiating other modalities

#### Scenario: Image extraction is its own module

- **WHEN** the multimodal pipeline extracts images
- **THEN** the logic MUST live in `app/services/document_processing/image_extraction.py`

#### Scenario: Chunking is its own module

- **WHEN** extracted text is chunked
- **THEN** the chunking rules MUST live in `app/services/document_processing/chunking.py` and operate on text returned by the extractors

#### Scenario: Storage handoff is its own module

- **WHEN** extracted images are persisted to `STORAGE_IMAGE_DIR`
- **THEN** the storage adapter MUST live in `app/services/document_processing/storage.py`

#### Scenario: Public import path is preserved

- **WHEN** any module imports `from app.services.document_processor import DocumentProcessor`
- **THEN** the import MUST resolve to a thin orchestrator that composes the per-modality modules
