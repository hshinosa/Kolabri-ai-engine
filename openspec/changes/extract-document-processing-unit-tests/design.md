# Design

## Test File Structure

### test_document_processing_text_extraction.py

```python
"""Direct unit tests for text_extraction module functions."""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock
from app.services.document_processing.text_extraction import (
    process_pdf, process_docx, process_pptx, process_text,
    _extract_images_from_docx,
)
from app.services.document_processing.models import ProcessedDocument

class TestProcessPdf:
    @pytest.mark.asyncio
    async def test_extracts_text_only(self):
        mock_fitz = MagicMock()
        mock_doc = self._make_doc(text="Hello world")
        mock_fitz.open.return_value = mock_doc

        result = await process_pdf(
            content=b"pdf-bytes",
            filename="test.pdf",
            document_id="doc-1",
            metadata={},
            ocr_available=False,
            vision_available=False,
            min_text_length_for_ocr=20,
            max_images_per_page=3,
            ocr_fn=AsyncMock(return_value=""),
            caption_fn=AsyncMock(return_value=""),
            create_chunks_fn=lambda text, **kw: [{"text": text}],
            _fitz=mock_fitz,
        )

        assert isinstance(result, ProcessedDocument)
        assert result.success is True
```

### test_document_processing_image_extraction.py

```python
"""Direct unit tests for image_extraction module functions."""

class TestProcessImage:
    @pytest.mark.asyncio
    async def test_image_with_vision_caption(self):
        result = await process_image(
            content=_large_png_bytes(),
            filename="test.png",
            document_id="doc-1",
            metadata={},
            vision_available=True,
            caption_fn=AsyncMock(return_value="A diagram"),
            create_chunks_fn=lambda text, **kw: [{"text": text}],
        )
        assert result.image_count == 1
        assert any("A diagram" in c.text for c in result.chunks)
```

## Coverage Targets

- `text_extraction.py`: line coverage > 90%
- `image_extraction.py`: line coverage > 90%
- Maintain `document_processor.py` coverage via existing `test_document_processor_full.py`

## Anti-Patterns to Avoid

- Tidak mock `DocumentProcessor` untuk test extracted functions
- Tidak duplicate semua test dari `test_document_processor_full.py` — fokus pada module-level edge cases
