## Context

`decompose-document-processor-by-modality` extracted `chunking.py` as pure functions (`clean_text`, `create_chunks`, `ChunkSpec`). The `DocumentProcessor` class remains at 1347 LOC with text extraction (PDF/DOCX/PPTX), OCR, multimodal image processing, and storage all mixed together. The modality boundaries are already clear from the existing private method grouping.

Existing package structure:
```
app/services/document_processing/
├── __init__.py          # re-exports ChunkSpec, clean_text, create_chunks
└── chunking.py          # pure functions
```

## Goals / Non-Goals

**Goals:**
- Extract `text_extraction.py` — PDF, DOCX, PPTX, plain text extraction functions.
- Extract `image_extraction.py` — image processing, caption generation, OCR functions.
- `document_processor.py` becomes thin orchestrator (~400 LOC) composing 3 modules.
- Public import path preserved.
- Per-modality unit tests.

**Non-Goals:**
- Extracting `storage.py` (`_store_chunks` is ~40 LOC, tightly coupled to MongoDB logger).
- Changing extraction behavior or chunking rules.
- Replacing OCR engine.

## Decisions

### D1: Extract as module-level functions, not classes
Following the chunking.py pattern — pure functions with explicit parameters. The orchestrator (`DocumentProcessor`) passes its state (settings, clients) as arguments.

### D2: text_extraction.py exports 4 processing functions
```python
async def process_pdf(content, filename, document_id, ...params) -> ProcessedDocument
async def process_docx(content, filename, document_id, ...params) -> ProcessedDocument
async def process_pptx(content, filename, document_id, ...params) -> ProcessedDocument
async def process_text(content, filename, document_id, file_type, ...params) -> ProcessedDocument
```
Plus helper: `_extract_images_from_docx`, `_process_extracted_images` (internal to the module).

### D3: image_extraction.py exports 5 functions
```python
async def process_image(content, filename, document_id, ...params) -> ProcessedDocument
async def generate_image_caption(image, llm_client) -> str
async def run_ocr(image, ocr_engine) -> str
async def run_ocr_optimized(image, ocr_engine) -> str
def initialize_ocr_engine(settings) -> Optional[PaddleOCR]
```
Plus `_run_page_ocr` internal helper.

### D4: Orchestrator passes state as parameters
The `DocumentProcessor` class retains its constructor (settings, LLM client, OCR engine). Each extracted function receives the specific dependencies it needs — no global state, no DI container.

### D5: Extract text_extraction first (larger, more tests)
Order: text_extraction.py → image_extraction.py → update orchestrator → tests.

## Risks / Trade-offs

- **Risk: OCR engine initialization coupling** — `PaddleOCR` is instantiated once in `__init__`. `image_extraction.py` receives the engine instance. No re-initialization needed.
- **Risk: `_process_pdf` is 130 LOC with mixed concerns** — text extraction + selective OCR + multimodal caption. Mitigation: the function stays in `text_extraction.py` as-is; it calls into `image_extraction.py` for OCR/caption parts.
- **Risk: test fixture paths** — existing tests mock `DocumentProcessor` methods. After extraction, mocks need updating. Mitigation: keep thin wrapper methods on `DocumentProcessor` that delegate to the module functions (for backwards compat).
