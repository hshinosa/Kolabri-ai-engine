"""
Image processing, OCR, and caption generation module.
"""

from __future__ import annotations

import io
import asyncio
import importlib.util
import logging
from typing import Optional

import numpy as np
from PIL import Image

from app.services.document_processing.models import ProcessedDocument

OCR_IMPORT_ERROR: Optional[str] = None
try:
    from paddleocr import PaddleOCR

    if importlib.util.find_spec("paddle") is None:
        raise ImportError("paddlepaddle is not installed")
    OCR_AVAILABLE = True
except ImportError as exc:
    PaddleOCR = None
    OCR_AVAILABLE = False
    OCR_IMPORT_ERROR = str(exc)

from app.core.config import settings
from app.core.logging import get_logger
from concurrent.futures import ThreadPoolExecutor

logger = get_logger(__name__)

_thread_pool = ThreadPoolExecutor(max_workers=2)

DEFAULT_MAX_IMAGE_SIZE = (1000, 1000)


def initialize_ocr_engine() -> Optional[PaddleOCR]:
    if not OCR_AVAILABLE:
        return None
    try:
        lang = getattr(settings, "OCR_LANGUAGE", None) or "en"
        engine = PaddleOCR(use_angle_cls=True, lang=lang)
        logging.getLogger("ppocr").setLevel(logging.ERROR)
        logger.info("PaddleOCR initialized", lang=lang)
        return engine
    except Exception:
        logger.exception("Failed to initialize PaddleOCR")
        return None


def run_paddle_ocr(image: Image.Image, ocr_engine: Optional[PaddleOCR]) -> str:
    if ocr_engine is None:
        return ""
    try:
        np_image = np.array(image)
        result = ocr_engine.ocr(np_image, cls=True)
    except Exception:
        logger.exception("ocr_failed")
        return ""
    finally:
        try:
            del np_image
        except NameError:
            pass

    if not result:
        return ""

    lines = []
    for line in result:
        for _, (text, confidence) in line:
            if not text:
                continue
            if confidence is not None and confidence < 0.4:
                continue
            lines.append(text.strip())

    return "\n".join(lines).strip()


async def run_ocr_optimized(
    image: Image.Image,
    *,
    ocr_available: bool,
    ocr_engine: Optional[PaddleOCR],
    max_image_size: tuple[int, int] = DEFAULT_MAX_IMAGE_SIZE,
) -> str:
    if not ocr_available:
        return ""

    try:
        if image.width > max_image_size[0] or image.height > max_image_size[1]:
            image.thumbnail(max_image_size, Image.Resampling.LANCZOS)

        original_image = image
        if image.mode != "RGB":
            image = image.convert("RGB")
            original_image.close()
            del original_image

        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(
            _thread_pool, lambda: run_paddle_ocr(image, ocr_engine)
        )

        return text.strip()
    except Exception:
        logger.exception("ocr_failed")
        return ""


async def run_ocr(
    image: Image.Image,
    *,
    ocr_available: bool,
    ocr_engine: Optional[PaddleOCR],
    max_image_size: tuple[int, int] = DEFAULT_MAX_IMAGE_SIZE,
) -> str:
    return await run_ocr_optimized(
        image,
        ocr_available=ocr_available,
        ocr_engine=ocr_engine,
        max_image_size=max_image_size,
    )


async def run_page_ocr(
    page,
    *,
    ocr_available: bool,
    ocr_engine: Optional[PaddleOCR],
    max_image_size: tuple[int, int] = DEFAULT_MAX_IMAGE_SIZE,
) -> str:
    import fitz

    if not ocr_available:
        return ""

    def render_page() -> Optional[Image.Image]:
        try:
            matrix = fitz.Matrix(1.5, 1.5)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            pix = None
            return image
        except Exception:
            logger.exception("page_render_failed")
            return None

    loop = asyncio.get_running_loop()
    image = await loop.run_in_executor(_thread_pool, render_page)
    if image is None:
        return ""

    try:
        return await run_ocr_optimized(
            image,
            ocr_available=ocr_available,
            ocr_engine=ocr_engine,
            max_image_size=max_image_size,
        )
    finally:
        del image


async def generate_image_caption(
    image: Image.Image,
    *,
    vision_client=None,
) -> str:
    if not vision_client:
        return ""

    try:
        prompt = (
            "Analisis gambar ini secara detail untuk keperluan materi kuliah.\n"
            "1. Jika ini DIAGRAM/SKEMA: Jelaskan alur dan komponennya.\n"
            "2. Jika ini GRAFIK: Jelaskan sumbu X/Y, tren, dan titik penting.\n"
            "3. Jika ini RUMUS: Tuliskan dalam format LaTeX.\n"
            "4. Abaikan jika gambar buram atau tidak bermakna.\n\n"
            "Outputkan hanya deskripsinya saja dalam Bahasa Indonesia."
        )

        img_buffer = io.BytesIO()
        prepared_image = image.convert("RGB") if image.mode != "RGB" else image
        prepared_image.save(img_buffer, format="JPEG", quality=85)
        img_bytes = img_buffer.getvalue()
        img_buffer.close()

        loop = asyncio.get_running_loop()

        import base64

        base64_image = base64.b64encode(img_bytes).decode("utf-8")
        response = await loop.run_in_executor(
            _thread_pool,
            lambda: vision_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                },
                            },
                        ],
                    }
                ],
                max_tokens=500,
            ),
        )

        if prepared_image is not image:
            prepared_image.close()

        return response.choices[0].message.content.strip()
    except Exception:
        logger.exception("vision_api_failed")
        return ""


async def process_image(
    content: bytes,
    filename: str,
    document_id: str,
    metadata: Optional[dict] = None,
    *,
    vision_available: bool,
    caption_fn=None,
    create_chunks_fn=None,
):

    if not vision_available:
        return ProcessedDocument(
            filename=filename,
            file_type="image",
            chunks=[],
            page_count=0,
            image_count=0,
            total_characters=0,
            processing_time_ms=0,
            success=False,
            error="Multimodal/Vision processing is disabled or unavailable",
        )

    img = None
    try:
        img = Image.open(io.BytesIO(content))
        caption = await caption_fn(img) if caption_fn else ""

        if not caption:
            raise ValueError("Vision AI failed to generate caption for image")

        full_text = f"=== [GAMBAR: {filename}] ===\nDeskripsi Visual: {caption}\n========================"

        chunks = (
            create_chunks_fn(
                text=full_text,
                document_id=document_id,
                filename=filename,
                page_number=1,
                metadata={**(metadata or {}), "is_multimodal": True},
            )
            if create_chunks_fn
            else []
        )

        return ProcessedDocument(
            filename=filename,
            file_type="image",
            chunks=chunks,
            page_count=1,
            image_count=1,
            total_characters=len(full_text),
            processing_time_ms=0,
            success=True,
        )
    except Exception:
        logger.exception("image_processing_failed", filename=filename)
        raise
    finally:
        if img is not None:
            img.close()
            del img
