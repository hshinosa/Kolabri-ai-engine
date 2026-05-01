"""Stable unit tests for document processor control flow under mocked heavy deps."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def doc_processor():
    with patch("app.services.document_processor.get_vector_store") as mock_vs:
        mock_vs.return_value = MagicMock()
        mock_vs.return_value.add_documents = AsyncMock()
        from app.services.document_processor import DocumentProcessor

        processor = DocumentProcessor()
        processor.ocr_available = False
        processor.vision_available = False
        processor._store_chunks = AsyncMock()
        yield processor


class TestCreateChunksNoInfiniteLoop:
    def test_short_text(self, doc_processor):
        chunks = doc_processor._create_chunks("Short text.", "doc1", "f.txt", 1)
        assert len(chunks) == 1

    def test_text_slightly_over_chunk_size(self, doc_processor):
        text = "A" * 1001
        chunks = doc_processor._create_chunks(text, "doc1", "f.txt", 1)
        assert len(chunks) >= 2

    def test_overlap_equals_chunk_size(self, doc_processor):
        original_overlap = doc_processor.chunk_overlap
        doc_processor.chunk_overlap = doc_processor.chunk_size
        try:
            chunks = doc_processor._create_chunks("Hello world. " * 200, "doc1", "f.txt", 1)
            assert len(chunks) >= 1
        finally:
            doc_processor.chunk_overlap = original_overlap


class TestDocumentProcessingMemory:
    @pytest.mark.asyncio
    async def test_text_file_processing(self, doc_processor):
        with patch.object(doc_processor, "_check_duplicate", return_value=None), patch.object(doc_processor, "_mark_processed"):
            result = await doc_processor.process_file(
                file_content=b"Hello world test content. " * 500,
                filename="test.txt",
                document_id="id1",
                metadata={},
            )
        assert result.success is True
        assert len(result.chunks) > 0

    @pytest.mark.asyncio
    async def test_file_path_text_processing(self, doc_processor, tmp_path):
        test_file = tmp_path / "data.txt"
        test_file.write_text("hello from file path")
        with patch.object(doc_processor, "_check_duplicate", return_value=None), patch.object(doc_processor, "_mark_processed"):
            result = await doc_processor.process_file(
                file_path=str(test_file),
                filename="data.txt",
                document_id="id2",
                metadata={},
            )
        assert result.success is True
        assert result.file_type == "text"

    @pytest.mark.asyncio
    async def test_process_pdf_routing_with_mock(self, doc_processor):
        doc_processor._process_pdf = AsyncMock(
            return_value=MagicMock(success=True, chunks=[], page_count=1, image_count=0, total_characters=0, processing_time_ms=0)
        )
        with patch.object(doc_processor, "_check_duplicate", return_value=None), patch.object(doc_processor, "_mark_processed"):
            result = await doc_processor.process_file(
                file_content=b"fake-pdf",
                filename="test.pdf",
                document_id="id3",
                metadata={},
            )
        assert result.success is True
        doc_processor._process_pdf.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sequential_processing(self, doc_processor):
        with patch.object(doc_processor, "_check_duplicate", return_value=None), patch.object(doc_processor, "_mark_processed"):
            for idx in range(3):
                result = await doc_processor.process_file(
                    file_content=f"content {idx}".encode(),
                    filename=f"test_{idx}.txt",
                    document_id=f"id_{idx}",
                    metadata={},
                )
                assert result.success is True
