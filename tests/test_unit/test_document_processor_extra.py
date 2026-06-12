import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.document_processor import DocumentProcessor


@pytest.fixture
def processor():
    with patch("app.services.document_processor.get_vector_store"):
        return DocumentProcessor()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ocr_available_check(processor):
    with (
        patch("app.services.document_processor.OCR_AVAILABLE", False),
        patch(
            "app.services.document_processor.importlib.util.find_spec",
            return_value=None,
        ),
    ):
        processor._ocr_engine = None
        processor._initialize_ocr_engine()
        assert processor.ocr_available is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vision_available_check(processor):
    with patch(
        "app.services.document_processor.importlib.util.find_spec", return_value=None
    ):
        # Trigger vision check (e.g. by checking if it is available)
        assert processor.vision_available is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_chunks_infinite_loop_regression(processor):
    # Bug fixed: start = max(end - self.chunk_overlap, start + 1)
    text = "A" * 1001
    processor.chunk_size = 1000
    processor.chunk_overlap = 200

    # This used to hang
    chunks = processor._create_chunks(text, "doc1", "test.txt", 1, {})
    assert len(chunks) > 1
