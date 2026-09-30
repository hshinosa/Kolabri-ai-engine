"""Regression tests for the asyncio.to_thread refactor (S2) and dead-code removal (S6).

Proves the ingest pipeline still completes end-to-end and that blocking work
(streaming hash, file reads, text decode) now runs off the event loop.
"""

import hashlib
import io
import threading
import zipfile
from unittest.mock import AsyncMock, patch

import pytest

from app.services.document_processor import DocumentProcessor

pytestmark = [pytest.mark.unit]


class _ThreadSpyBytes(bytes):
    """Bytes subclass that records which thread performs text decoding."""

    decode_threads: list = []

    def decode(self, encoding="utf-8", errors="strict"):
        _ThreadSpyBytes.decode_threads.append(threading.get_ident())
        return super().decode(encoding, errors)


@pytest.fixture
def processor():
    with (
        patch("app.services.document_processor.get_vector_store"),
        patch("app.services.document_processor.PaddleOCR"),
    ):
        proc = DocumentProcessor()
    proc.ocr_available = False
    proc._store_chunks = AsyncMock()
    return proc


@pytest.mark.asyncio
async def test_process_file_in_memory_txt_completes_off_loop(processor):
    """A small in-memory txt file flows through process_file; decode runs in a worker thread."""
    _ThreadSpyBytes.decode_threads = []
    content = _ThreadSpyBytes(b"Hello async doc pipeline. " * 40)

    result = await processor.process_file(
        file_content=content,
        filename="notes.txt",
        document_id="doc-txt",
        collection_name="col",
    )

    assert result.success is True
    assert result.file_type == "text"
    assert result.chunks
    assert result.total_characters == len(content)

    # Decode must NOT run on the event loop's thread
    assert _ThreadSpyBytes.decode_threads, "decode never ran"
    main_thread = threading.get_ident()
    assert all(tid != main_thread for tid in _ThreadSpyBytes.decode_threads)

    # Sanity: the spy did not corrupt the content
    assert content.decode() == "Hello async doc pipeline. " * 40


@pytest.mark.asyncio
async def test_process_file_from_path_hash_and_read_run_off_loop(processor, tmp_path):
    """Streaming hash + file read for file_path inputs happen in worker threads."""
    f = tmp_path / "data.txt"
    f.write_bytes(b"Isi dokumen untuk pengujian. " * 30)

    hash_threads = []
    orig_hash = processor._compute_content_hash_from_path

    def spy_hash(path):
        hash_threads.append(threading.get_ident())
        return orig_hash(path)

    read_threads = []
    orig_read = DocumentProcessor._read_file_bytes

    def spy_read(path):
        read_threads.append(threading.get_ident())
        return orig_read(path)

    processor._compute_content_hash_from_path = spy_hash
    processor._read_file_bytes = spy_read

    result = await processor.process_file(
        filename="data.txt",
        document_id="doc-path",
        collection_name="col",
        file_path=str(f),
    )

    assert result.success is True
    assert result.chunks

    main_thread = threading.get_ident()
    assert hash_threads and hash_threads[0] != main_thread
    assert read_threads and read_threads[0] != main_thread

    # The spy returns the real sha256 of the file bytes
    expected = hashlib.sha256(b"Isi dokumen untuk pengujian. " * 30).hexdigest()
    assert spy_hash(str(f)) == expected


@pytest.mark.asyncio
async def test_process_file_in_memory_zip_completes(processor):
    """A small in-memory zip exercises the to_thread zip write/extract/cleanup path."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("docs/bab1.txt", "Isi bab satu. " * 50)
    zip_bytes = buf.getvalue()

    result = await processor.process_file(
        file_content=zip_bytes,
        filename="modul.zip",
        document_id="doc-zip",
        collection_name="col",
    )

    assert result.success is True
    assert result.file_type == "zip"
    assert result.page_count == 1  # the single member was processed
