import io
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.fixture(autouse=True)
def _patch_pil_image():
    _Image = sys.modules.get("PIL.Image")
    with patch("app.services.document_processing.image_extraction.Image", _Image):
        yield


def _get_image():
    return sys.modules.get("PIL.Image")
from app.services.document_processing.image_extraction import (
    process_image,
    generate_image_caption,
    run_paddle_ocr,
    run_ocr_optimized,
    initialize_ocr_engine,
)
from app.services.document_processing.models import ProcessedDocument


def _large_png_bytes():
    img = _get_image().new("RGB", (300, 300), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img.close()
    return buf.getvalue()


def _fake_create_chunks(text, **kwargs):
    from app.services.document_processing.chunking import ChunkSpec
    return [ChunkSpec(text=text[:100], metadata={}, chunk_id="c1")]


class TestProcessImage:
    @pytest.mark.asyncio
    async def test_with_vision_caption(self):
        result = await process_image(
            content=_large_png_bytes(),
            filename="test.png",
            document_id="d1",
            metadata={},
            vision_available=True,
            caption_fn=AsyncMock(return_value="A diagram of X"),
            create_chunks_fn=_fake_create_chunks,
        )

        assert isinstance(result, ProcessedDocument)
        assert result.success is True
        assert result.image_count == 1
        assert any("A diagram" in c.text for c in result.chunks)

    @pytest.mark.asyncio
    async def test_vision_disabled(self):
        result = await process_image(
            content=_large_png_bytes(),
            filename="test.png",
            document_id="d1",
            metadata={},
            vision_available=False,
            caption_fn=AsyncMock(return_value=""),
            create_chunks_fn=_fake_create_chunks,
        )

        assert result.success is False
        assert "disabled" in result.error.lower() or "unavailable" in result.error.lower()


class TestGenerateImageCaption:
    @pytest.mark.asyncio
    async def test_with_vision_model(self):
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "  Caption text  "
        mock_model.generate_content.return_value = mock_response
        img = _get_image().new("RGB", (10, 10))

        result = await generate_image_caption(
            img, vision_model=mock_model, vision_client=None,
        )

        assert result == "Caption text"

    @pytest.mark.asyncio
    async def test_no_model(self):
        img = _get_image().new("RGB", (10, 10))
        result = await generate_image_caption(img, vision_model=None, vision_client=None)
        assert result == ""


class TestRunPaddleOcr:
    def test_with_engine(self):
        mock_engine = MagicMock()
        mock_engine.ocr.return_value = [
            [("line1", ("text1", 0.9)), ("line2", ("text2", 0.8))]
        ]
        img = _get_image().new("RGB", (100, 100))

        result = run_paddle_ocr(img, mock_engine)

        assert "text1" in result
        assert "text2" in result

    def test_no_engine(self):
        img = _get_image().new("RGB", (100, 100))
        result = run_paddle_ocr(img, None)
        assert result == ""

    def test_engine_returns_none(self):
        mock_engine = MagicMock()
        mock_engine.ocr.return_value = None
        img = _get_image().new("RGB", (100, 100))

        result = run_paddle_ocr(img, mock_engine)
        assert result == ""


class TestRunOcrOptimized:
    @pytest.mark.asyncio
    async def test_disabled(self):
        img = _get_image().new("RGB", (100, 100))
        result = await run_ocr_optimized(
            img, ocr_available=False, ocr_engine=None,
        )
        assert result == ""

    @pytest.mark.asyncio
    async def test_with_engine(self):
        mock_engine = MagicMock()
        mock_engine.ocr.return_value = [[("w", ("recognized", 0.9))]]
        img = _get_image().new("RGB", (100, 100))

        import asyncio
        loop = asyncio.get_event_loop()
        async def fake_exec(pool, func):
            return func()
        with patch.object(loop, "run_in_executor", side_effect=fake_exec):
            result = await run_ocr_optimized(
                img, ocr_available=True, ocr_engine=mock_engine,
            )

        assert result == "recognized"


class TestInitializeOcrEngine:
    def test_disabled(self):
        with patch("app.services.document_processing.image_extraction.OCR_AVAILABLE", False):
            result = initialize_ocr_engine()
        assert result is None
