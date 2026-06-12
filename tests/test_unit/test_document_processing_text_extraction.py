import io
import sys
import zipfile
from unittest.mock import AsyncMock, MagicMock, Mock, patch
import pytest


@pytest.fixture(autouse=True)
def _patch_pil_image():
    _Image = sys.modules.get("PIL.Image")
    with patch("app.services.document_processing.text_extraction.Image", _Image):
        yield


def _get_image():
    return sys.modules.get("PIL.Image")


from app.services.document_processing.text_extraction import (
    process_pdf,
    process_docx,
    process_pptx,
    process_text,
    _extract_images_from_docx,
)
from app.services.document_processing.models import ProcessedDocument


def _make_mock_page(text="Hello world", images=None):
    page = MagicMock()
    page.get_text.return_value = text
    page.get_images.return_value = images or []
    return page


def _make_mock_pdf_doc(pages):
    doc = MagicMock()
    doc.__len__ = Mock(return_value=len(pages))
    doc.__iter__ = Mock(return_value=iter(pages))
    doc.__enter__ = Mock(return_value=doc)
    doc.__exit__ = Mock(return_value=False)
    return doc


def _tiny_png_bytes():
    img = _get_image().new("RGB", (4, 4), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img.close()
    return buf.getvalue()


def _large_png_bytes():
    img = _get_image().new("RGB", (300, 300), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img.close()
    return buf.getvalue()


def _fake_create_chunks(text, **kwargs):
    from app.services.document_processing.chunking import ChunkSpec

    return [ChunkSpec(text=text[:100], metadata={}, chunk_id="c1")]


class TestProcessPdf:
    @pytest.mark.asyncio
    async def test_text_only(self):
        page = _make_mock_page(text="Hello world " * 20)
        doc = _make_mock_pdf_doc([page])
        mock_fitz = MagicMock()
        mock_fitz.open.return_value = doc

        result = await process_pdf(
            content=b"pdf",
            filename="test.pdf",
            document_id="d1",
            metadata={},
            ocr_available=False,
            vision_available=False,
            min_text_length_for_ocr=20,
            max_images_per_page=3,
            chunk_size=1000,
            chunk_overlap=200,
            ocr_fn=AsyncMock(return_value=""),
            caption_fn=AsyncMock(return_value=""),
            _fitz=mock_fitz,
        )

        assert isinstance(result, ProcessedDocument)
        assert result.success is True
        assert result.page_count == 1
        assert len(result.chunks) > 0

    @pytest.mark.asyncio
    async def test_with_image_processing(self):
        page = _make_mock_page(text="Short", images=[(42,)])
        page.get_text.return_value = (
            "Some page text that is long enough to skip ocr threshold limit."
        )
        doc = _make_mock_pdf_doc([page])
        doc.extract_image.return_value = {"image": _large_png_bytes()}
        mock_fitz = MagicMock()
        mock_fitz.open.return_value = doc

        result = await process_pdf(
            content=b"pdf",
            filename="test.pdf",
            document_id="d1",
            metadata={},
            ocr_available=False,
            vision_available=True,
            min_text_length_for_ocr=20,
            max_images_per_page=3,
            chunk_size=1000,
            chunk_overlap=200,
            ocr_fn=AsyncMock(return_value=""),
            caption_fn=AsyncMock(return_value="A diagram"),
            _fitz=mock_fitz,
        )

        assert result.success is True
        assert result.image_count >= 1

    @pytest.mark.asyncio
    async def test_ocr_fallback_appends_when_page_text_short(self):
        page = _make_mock_page(text="hi")
        doc = _make_mock_pdf_doc([page])
        mock_fitz = MagicMock()
        mock_fitz.open.return_value = doc
        ocr_fn = AsyncMock(return_value="scanned words from page")

        result = await process_pdf(
            content=b"pdf",
            filename="test.pdf",
            document_id="d1",
            metadata={},
            ocr_available=True,
            vision_available=False,
            min_text_length_for_ocr=20,
            max_images_per_page=3,
            chunk_size=1000,
            chunk_overlap=200,
            ocr_fn=ocr_fn,
            caption_fn=AsyncMock(return_value=""),
            _fitz=mock_fitz,
        )

        ocr_fn.assert_awaited_once()
        assert result.success is True
        combined = " ".join(c.text for c in result.chunks)
        assert "[OCR]" in combined or "scanned" in combined

    @pytest.mark.asyncio
    async def test_ocr_empty_does_not_append_ocr_block(self):
        page = _make_mock_page(text="x")
        doc = _make_mock_pdf_doc([page])
        mock_fitz = MagicMock()
        mock_fitz.open.return_value = doc

        result = await process_pdf(
            content=b"pdf",
            filename="test.pdf",
            document_id="d1",
            metadata={},
            ocr_available=True,
            vision_available=False,
            min_text_length_for_ocr=20,
            max_images_per_page=3,
            chunk_size=1000,
            chunk_overlap=200,
            ocr_fn=AsyncMock(return_value=""),
            caption_fn=AsyncMock(return_value=""),
            _fitz=mock_fitz,
        )

        assert result.success is True
        assert "[OCR]" not in " ".join(c.text for c in result.chunks)

    @pytest.mark.asyncio
    async def test_caption_callback_empty_skips_image_caption(self):
        page = _make_mock_page(
            text="Enough native text here to avoid OCR path entirely for this page."
        )
        doc = _make_mock_pdf_doc([page])
        doc.extract_image.return_value = {"image": _large_png_bytes()}
        mock_fitz = MagicMock()
        mock_fitz.open.return_value = doc
        caption_fn = AsyncMock(return_value="")

        result = await process_pdf(
            content=b"pdf",
            filename="test.pdf",
            document_id="d1",
            metadata={},
            ocr_available=False,
            vision_available=True,
            min_text_length_for_ocr=20,
            max_images_per_page=3,
            chunk_size=1000,
            chunk_overlap=200,
            ocr_fn=AsyncMock(return_value=""),
            caption_fn=caption_fn,
            _fitz=mock_fitz,
        )

        assert result.success is True
        assert "[Image]" not in " ".join(c.text for c in result.chunks)

    @pytest.mark.asyncio
    async def test_empty_content(self):
        with pytest.raises(ValueError, match="content or file_path"):
            await process_pdf(
                content=None,
                filename="test.pdf",
                document_id="d1",
                metadata={},
                ocr_available=False,
                vision_available=False,
                min_text_length_for_ocr=20,
                max_images_per_page=3,
                chunk_size=1000,
                chunk_overlap=200,
                ocr_fn=AsyncMock(return_value=""),
                caption_fn=AsyncMock(return_value=""),
            )


class TestProcessDocx:
    @pytest.mark.asyncio
    async def test_simple_docx(self):
        mock_doc = MagicMock()
        mock_para1 = MagicMock()
        mock_para1.text = "Hello world " * 20
        mock_para2 = MagicMock()
        mock_para2.text = ""
        mock_doc.paragraphs = [mock_para1, mock_para2]
        mock_doc.tables = []

        result = await process_docx(
            content=b"docx",
            filename="test.docx",
            document_id="d1",
            metadata={},
            chunk_size=1000,
            chunk_overlap=200,
            _DocxDocument=lambda _: mock_doc,
            _extract_images_fn=lambda _: [],
        )

        assert result.success is True
        assert len(result.chunks) > 0


class TestProcessText:
    @pytest.mark.asyncio
    async def test_plain_text(self):
        result = await process_text(
            content=b"Hello world " * 50,
            filename="test.txt",
            document_id="d1",
            file_type="text",
            metadata={},
            chunk_size=1000,
            chunk_overlap=200,
        )

        assert result.success is True
        assert len(result.chunks) > 0


class TestExtractImagesFromDocx:
    def test_extracts_images(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("word/media/image1.png", _tiny_png_bytes())
            zf.writestr("word/document.xml", "<doc/>")
        content = buf.getvalue()

        images = list(_extract_images_from_docx(content))
        assert len(images) == 1
        for img in images:
            img.close()

    def test_corrupt_zip(self):
        images = list(_extract_images_from_docx(b"not-a-zip"))
        assert len(images) == 0

    def test_no_media_files(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("word/document.xml", "<doc/>")
        content = buf.getvalue()

        images = list(_extract_images_from_docx(content))
        assert len(images) == 0
