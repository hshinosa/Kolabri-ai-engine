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
        assert (
            "disabled" in result.error.lower() or "unavailable" in result.error.lower()
        )


class TestGenerateImageCaption:
    @pytest.mark.asyncio
    async def test_with_vision_client_rgb_image(self):
        img = _get_image().new("RGB", (10, 10), color="white")
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "  Client caption  "
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        result = await generate_image_caption(img, vision_client=mock_client)

        assert result == "Client caption"
        mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_vision_client_non_rgb_image(self):
        img = _get_image().new("RGBA", (10, 10), color=(255, 0, 0, 128))
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "Alpha caption"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        result = await generate_image_caption(img, vision_client=mock_client)

        assert result == "Alpha caption"
        mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_vision_client_error_returns_empty(self):
        img = _get_image().new("RGB", (10, 10))
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("boom")

        result = await generate_image_caption(img, vision_client=mock_client)

        assert result == ""

    @pytest.mark.asyncio
    async def test_no_model(self):
        img = _get_image().new("RGB", (10, 10))
        result = await generate_image_caption(img, vision_client=None)
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
            img,
            ocr_available=False,
            ocr_engine=None,
        )
        assert result == ""

    @pytest.mark.asyncio
    async def test_large_non_rgb_image_and_engine(self):
        img = _get_image().new("RGBA", (1200, 1200), color=(0, 128, 255, 255))
        mock_engine = MagicMock()
        mock_engine.ocr.return_value = [[("w", ("scanned", 0.9))]]

        import asyncio

        loop = asyncio.get_event_loop()

        async def fake_exec(pool, func):
            return func()

        with patch.object(loop, "run_in_executor", side_effect=fake_exec):
            result = await run_ocr_optimized(
                img,
                ocr_available=True,
                ocr_engine=mock_engine,
            )

        assert result == "scanned"

    @pytest.mark.asyncio
    async def test_engine_exception_returns_empty(self):
        img = _get_image().new("RGB", (100, 100))
        mock_engine = MagicMock()
        mock_engine.ocr.side_effect = RuntimeError("ocr failed")

        import asyncio

        loop = asyncio.get_event_loop()

        async def fake_exec(pool, func):
            return func()

        with patch.object(loop, "run_in_executor", side_effect=fake_exec):
            result = await run_ocr_optimized(
                img,
                ocr_available=True,
                ocr_engine=mock_engine,
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
                img,
                ocr_available=True,
                ocr_engine=mock_engine,
            )

        assert result == "recognized"


class TestInitializeOcrEngine:
    def test_disabled(self):
        with patch(
            "app.services.document_processing.image_extraction.OCR_AVAILABLE", False
        ):
            result = initialize_ocr_engine()
        assert result is None

    def test_init_success(self):
        mock_engine = MagicMock()
        with (
            patch(
                "app.services.document_processing.image_extraction.OCR_AVAILABLE",
                True,
            ),
            patch(
                "app.services.document_processing.image_extraction.PaddleOCR",
                return_value=mock_engine,
            ),
            patch("app.services.document_processing.image_extraction.settings") as st,
        ):
            st.OCR_LANGUAGE = "en"
            assert initialize_ocr_engine() is mock_engine

    def test_init_failure_returns_none(self):
        with (
            patch(
                "app.services.document_processing.image_extraction.OCR_AVAILABLE",
                True,
            ),
            patch(
                "app.services.document_processing.image_extraction.PaddleOCR",
                side_effect=RuntimeError("paddle fail"),
            ),
        ):
            assert initialize_ocr_engine() is None


class TestRunOcrWrapper:
    @pytest.mark.asyncio
    async def test_run_ocr_delegates_to_optimized(self):
        img = _get_image().new("RGB", (50, 50))
        with patch(
            "app.services.document_processing.image_extraction.run_ocr_optimized",
            new_callable=AsyncMock,
            return_value="ok",
        ) as opt:
            from app.services.document_processing.image_extraction import run_ocr

            out = await run_ocr(img, ocr_available=True, ocr_engine=MagicMock())
        assert out == "ok"
        opt.assert_awaited_once()


class TestRunPageOcr:
    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self):
        from app.services.document_processing.image_extraction import run_page_ocr

        assert (
            await run_page_ocr(MagicMock(), ocr_available=False, ocr_engine=None) == ""
        )

    @pytest.mark.asyncio
    async def test_render_failure_returns_empty(self):
        from app.services.document_processing.image_extraction import run_page_ocr

        loop = __import__("asyncio").get_event_loop()

        async def fake_exec(_pool, func):
            return func()

        with patch.object(loop, "run_in_executor", side_effect=fake_exec):
            out = await run_page_ocr(
                MagicMock(),
                ocr_available=True,
                ocr_engine=MagicMock(),
            )
        assert out == ""


class TestRunPaddleOcrExtra:
    def test_ocr_exception_returns_empty(self):
        mock_engine = MagicMock()
        mock_engine.ocr.side_effect = RuntimeError("ocr boom")
        img = _get_image().new("RGB", (10, 10))
        assert run_paddle_ocr(img, mock_engine) == ""


class TestProcessImageBranches:
    @pytest.mark.asyncio
    async def test_caption_fn_empty_raises_failure(self):
        with pytest.raises(ValueError, match="failed to generate caption"):
            await process_image(
                content=_large_png_bytes(),
                filename="test.png",
                document_id="d1",
                metadata={"course": "math"},
                vision_available=True,
                caption_fn=AsyncMock(return_value=""),
                create_chunks_fn=_fake_create_chunks,
            )

    @pytest.mark.asyncio
    async def test_no_chunk_fn_returns_success(self):
        result = await process_image(
            content=_large_png_bytes(),
            filename="test.png",
            document_id="d1",
            metadata={"course": "math"},
            vision_available=True,
            caption_fn=AsyncMock(return_value="A diagram"),
            create_chunks_fn=None,
        )

        assert result.success is True
        assert result.chunks == []
