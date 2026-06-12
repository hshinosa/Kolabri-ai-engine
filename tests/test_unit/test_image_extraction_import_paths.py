"""Cover optional PaddleOCR import paths in image_extraction."""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


def test_ocr_import_error_when_paddle_missing():
    fake_paddleocr = MagicMock()
    with patch.dict(sys.modules, {"paddleocr": fake_paddleocr}):
        with patch("importlib.util.find_spec", return_value=None):
            mod = importlib.import_module(
                "app.services.document_processing.image_extraction"
            )
            importlib.reload(mod)
    assert mod.OCR_AVAILABLE is False
    assert mod.PaddleOCR is None


def test_run_paddle_ocr_nameerror_on_del_np_image():
    from app.services.document_processing.image_extraction import run_paddle_ocr

    mock_engine = MagicMock()
    mock_engine.ocr.side_effect = RuntimeError("fail before np_image")
    img = sys.modules["PIL"].Image.new("RGB", (5, 5))
    assert run_paddle_ocr(img, mock_engine) == ""
