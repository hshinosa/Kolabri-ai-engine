# Image Processing Consolidation

## MODIFIED Requirements

### Requirement: Single source of truth for image processing

`DocumentProcessor` SHALL NOT contain image processing, OCR, or caption generation logic. All such logic MUST live in `app/services/document_processing/image_extraction.py` as module-level functions.

#### Scenario: Image processing call

- Given `DocumentProcessor.process_file` receives an image file
- When the processor needs to extract OCR text or generate captions
- Then it MUST call `image_extraction.process_image(...)` directly
- And MUST NOT have its own `_process_image`, `_generate_image_caption`, `_run_ocr*` methods

#### Scenario: Test mocking strategy

- Given a unit test for `DocumentProcessor.process_file` with image inputs
- When the test needs to mock OCR or caption generation
- Then the test MUST patch module-level functions (e.g., `image_extraction.run_paddle_ocr`)
- And MUST NOT mock instance methods on `DocumentProcessor`
