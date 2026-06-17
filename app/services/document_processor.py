"""
Document Processor Service
==========================
Comprehensive document processing supporting multiple formats:
- PDF (with text and image extraction + OCR)
- DOCX (Microsoft Word)
- PPTX (Microsoft PowerPoint)
- TXT, MD (Plain text and Markdown)
- ZIP (Archive containing multiple documents)

Optimized for:
- Memory efficiency (streaming where possible)
- Parallel processing for batch operations
- Selective OCR (only when text extraction fails)
"""

import os
import io
import re
import zipfile
import tempfile
import asyncio
import gc
import shutil
import logging
import importlib.util
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
from concurrent.futures import ThreadPoolExecutor

from app.services.document_processing.models import ProcessedDocument, ProcessedChunk

# Multimodal / Vision
VISION_AVAILABLE = False

# PDF Processing
from pypdf import PdfReader
import fitz  # PyMuPDF for image extraction

# Document Processing
from docx import Document as DocxDocument
from pptx import Presentation

# Image Processing
import numpy as np
from PIL import Image

# OCR (optional - graceful fallback if not available)
OCR_IMPORT_ERROR: Optional[str] = None
try:
    from paddleocr import PaddleOCR

    # Ensure paddle core dependency is present
    if importlib.util.find_spec("paddle") is None:
        raise ImportError("paddlepaddle is not installed")

    OCR_AVAILABLE = True
except ImportError as exc:
    PaddleOCR = None  # type: ignore
    OCR_AVAILABLE = False
    OCR_IMPORT_ERROR = str(exc)

from app.core.config import settings
from app.core.logging import get_logger
from app.services.vector_store import get_vector_store

logger = get_logger(__name__)

# Thread pool for CPU-bound tasks
_thread_pool = ThreadPoolExecutor(max_workers=2)


@dataclass
class BatchProcessResult:
    """Result of batch processing multiple documents."""

    total_files: int
    successful_files: int
    failed_files: int
    total_chunks: int
    documents: List[ProcessedDocument]
    processing_time_ms: float


class DocumentProcessor:
    """
    Comprehensive document processor with support for multiple formats.

    Features:
    - Multi-format support (PDF, DOCX, PPTX, TXT, MD)
    - ZIP archive extraction and batch processing
    - PDF image extraction with OCR (optimized)
    - Smart text chunking with overlap
    - Metadata extraction
    - Memory-optimized processing
    - Content hash-based idempotency check

    Optimizations:
    - Uses temp files for large ZIPs instead of memory
    - Parallel processing for multiple files
    - Selective OCR only when text extraction yields little content
    - Batch vector store operations
    - Garbage collection for large files
    """

    # Supported file extensions
    SUPPORTED_EXTENSIONS = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".doc": "docx",  # Will attempt to process as docx
        ".pptx": "pptx",
        ".ppt": "pptx",  # Will attempt to process as pptx
        ".txt": "text",
        ".md": "markdown",
        ".markdown": "markdown",
        ".zip": "zip",
        ".jpg": "image",
        ".jpeg": "image",
        ".png": "image",
    }

    # OCR settings
    MIN_TEXT_LENGTH_FOR_OCR = 50  # Only OCR if page has less text than this
    MAX_IMAGES_PER_PAGE = 3  # Limit images to OCR per page
    MAX_IMAGE_SIZE = (1000, 1000)  # Resize large images before OCR

    # Parallel processing settings
    MAX_PARALLEL_FILES = 1  # Process sequentially to reduce peak memory

    def __init__(self, provider_context: Optional[Dict[str, Any]] = None):
        self._provider_context = provider_context
        self.chunk_size = settings.CHUNK_SIZE
        self.chunk_overlap = settings.CHUNK_OVERLAP
        self.max_file_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        self.max_zip_size = settings.MAX_ZIP_SIZE_MB * 1024 * 1024
        self.ocr_available = OCR_AVAILABLE and settings.ENABLE_OCR
        self.vision_available = (
            VISION_AVAILABLE and settings.ENABLE_MULTIMODAL_PROCESSING
        )
        self._ocr_engine = None
        self._vision_client = None

        # Idempotency: Track processed content hashes
        self._processed_hashes: Dict[str, str] = {}  # hash -> document_id

        if self.ocr_available:
            from app.services.document_processing.image_extraction import (
                initialize_ocr_engine,
            )

            self._ocr_engine = initialize_ocr_engine()

        if self.vision_available:
            auth = (self._provider_context or {}).get("auth", {})
            execution = (self._provider_context or {}).get("execution", {})
            api_key = auth.get("credential")
            base_url = execution.get("baseUrl")
            if api_key and base_url:
                from openai import OpenAI

                self._vision_client = OpenAI(
                    api_key=api_key,
                    base_url=base_url,
                )
                logger.info(
                    "OpenAI Vision initialized",
                    model=execution.get("model"),
                )
        elif settings.ENABLE_OCR:
            if OCR_IMPORT_ERROR:
                logger.warning(
                    "OCR disabled: PaddleOCR dependency unavailable",
                    reason=OCR_IMPORT_ERROR,
                )
            else:
                logger.info("OCR fallback (PaddleOCR) available")
        else:
            logger.info("OCR disabled via configuration")

    def _compute_content_hash(self, content: bytes) -> str:
        """Compute SHA256 hash of file content for idempotency check."""
        return hashlib.sha256(content).hexdigest()

    def _check_duplicate(
        self, content_hash: str, collection_name: str
    ) -> Optional[str]:
        """
        Check if content has already been processed.

        Returns:
            document_id if duplicate, None otherwise
        """
        cache_key = f"{collection_name}:{content_hash}"
        return self._processed_hashes.get(cache_key)

    def _mark_processed(
        self, content_hash: str, collection_name: str, document_id: str
    ) -> None:
        """Mark content as processed for idempotency."""
        cache_key = f"{collection_name}:{content_hash}"
        self._processed_hashes[cache_key] = document_id

        # Prevent unbounded growth (keep last 10000 entries)
        if len(self._processed_hashes) > 10000:
            # Remove oldest entries (first 1000)
            keys_to_remove = list(self._processed_hashes.keys())[:1000]
            for key in keys_to_remove:
                del self._processed_hashes[key]

    def _compute_content_hash_from_path(self, file_path: str) -> str:
        """Compute SHA256 hash by streaming from disk (avoids loading entire file into RAM)."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def _read_file_bytes(file_path: Optional[str]) -> bytes:
        """Read file from disk into bytes. Only used when streaming is not possible."""
        if file_path is None:
            raise ValueError("file_path is required when file_content is not provided")
        with open(file_path, "rb") as f:
            return f.read()

    async def process_file(
        self,
        file_content: Optional[bytes] = None,
        filename: str = "",
        document_id: str = "",
        collection_name: str = "",
        course_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        file_path: Optional[str] = None,
    ) -> ProcessedDocument:
        """
        Process a single file of any supported type.

        Args:
            file_content: Raw file bytes (optional if file_path is provided)
            filename: Original filename
            document_id: Unique document identifier
            collection_name: Vector store collection name
            course_id: Optional course ID
            metadata: Optional additional metadata
            file_path: Optional path to file on disk (avoids loading into RAM)

        Returns:
            ProcessedDocument with chunks and stats
        """
        start_time = datetime.now()

        # If file_path is provided but no content, read only what's needed for hash
        if file_content is None and file_path is not None:
            # Compute hash by streaming the file instead of loading all into RAM
            content_hash = self._compute_content_hash_from_path(file_path)
            file_size = os.path.getsize(file_path)
        elif file_content is not None:
            content_hash = self._compute_content_hash(file_content)
            file_size = len(file_content)
        else:
            return ProcessedDocument(
                filename=filename,
                file_type="unknown",
                chunks=[],
                page_count=0,
                image_count=0,
                total_characters=0,
                processing_time_ms=0,
                success=False,
                error="Either file_content or file_path must be provided",
            )

        # Get file extension and type
        ext = Path(filename).suffix.lower()
        file_type = self.SUPPORTED_EXTENSIONS.get(ext)

        if not file_type:
            return ProcessedDocument(
                filename=filename,
                file_type="unknown",
                chunks=[],
                page_count=0,
                image_count=0,
                total_characters=0,
                processing_time_ms=0,
                success=False,
                error=f"Unsupported file type: {ext}",
            )

        # Idempotency check: Skip if identical content already processed
        existing_doc_id = self._check_duplicate(content_hash, collection_name)
        if existing_doc_id:
            logger.info(
                "document_already_processed",
                filename=filename,
                content_hash=content_hash[:16],
                existing_doc_id=existing_doc_id,
            )
            return ProcessedDocument(
                filename=filename,
                file_type=file_type,
                chunks=[],
                page_count=0,
                image_count=0,
                total_characters=0,
                processing_time_ms=0,
                success=True,
                error=f"Document already processed as {existing_doc_id}",
            )

        # Validate file size (use larger limit for ZIP files)
        max_size = self.max_zip_size if file_type == "zip" else self.max_file_size
        max_size_mb = (
            settings.MAX_ZIP_SIZE_MB
            if file_type == "zip"
            else settings.MAX_FILE_SIZE_MB
        )

        if file_size > max_size:
            return ProcessedDocument(
                filename=filename,
                file_type=file_type,
                chunks=[],
                page_count=0,
                image_count=0,
                total_characters=0,
                processing_time_ms=0,
                success=False,
                error=f"File size exceeds {max_size_mb}MB limit",
            )

        try:
            # Process based on file type
            if file_type == "pdf":
                result = await self._process_pdf(
                    file_content, filename, document_id, metadata, file_path=file_path
                )
            elif file_type == "docx":
                # DOCX/PPTX/text still need bytes; only load if not already provided
                content_for_processing = (
                    file_content
                    if file_content is not None
                    else self._read_file_bytes(file_path)
                )
                result = await self._process_docx(
                    content_for_processing, filename, document_id, metadata
                )
                if file_content is None:
                    del content_for_processing
                    gc.collect()
            elif file_type == "pptx":
                content_for_processing = (
                    file_content
                    if file_content is not None
                    else self._read_file_bytes(file_path)
                )
                result = await self._process_pptx(
                    content_for_processing, filename, document_id, metadata
                )
                if file_content is None:
                    del content_for_processing
                    gc.collect()
            elif file_type in ("text", "markdown"):
                content_for_processing = (
                    file_content
                    if file_content is not None
                    else self._read_file_bytes(file_path)
                )
                result = await self._process_text(
                    content_for_processing, filename, document_id, file_type, metadata
                )
                if file_content is None:
                    del content_for_processing
                    gc.collect()
            elif file_type == "zip":
                # ZIP processing returns multiple documents
                content_for_processing = (
                    file_content
                    if file_content is not None
                    else self._read_file_bytes(file_path)
                )
                batch_result = await self.process_zip(
                    content_for_processing,
                    document_id,
                    collection_name,
                    course_id,
                    metadata,
                )
                if file_content is None:
                    del content_for_processing
                    gc.collect()
                # Aggregate results
                total_chunks = sum(len(doc.chunks) for doc in batch_result.documents)
                return ProcessedDocument(
                    filename=filename,
                    file_type="zip",
                    chunks=[],  # Return empty list, they are already stored
                    page_count=batch_result.total_files,
                    image_count=0,
                    total_characters=sum(
                        doc.total_characters for doc in batch_result.documents
                    ),
                    processing_time_ms=batch_result.processing_time_ms,
                    success=batch_result.successful_files > 0,
                    error=None
                    if batch_result.successful_files > 0
                    else "No files processed successfully",
                )
            elif file_type == "image":
                content_for_processing = (
                    file_content
                    if file_content is not None
                    else self._read_file_bytes(file_path)
                )
                result = await self._process_image(
                    content_for_processing, filename, document_id, metadata
                )
                if file_content is None:
                    del content_for_processing
                    gc.collect()
            else:
                raise ValueError(f"Handler not implemented for type: {file_type}")

            # Store chunks in vector store
            if result.chunks:
                await self._store_chunks(result.chunks, collection_name)

            # Mark as processed for idempotency
            self._mark_processed(content_hash, collection_name, document_id)

            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result.processing_time_ms = processing_time

            logger.info(
                "document_processed",
                filename=filename,
                file_type=file_type,
                chunks=len(result.chunks),
                pages=result.page_count,
                images=result.image_count,
                processing_time_ms=processing_time,
                content_hash=content_hash[:16],
            )

            return result

        except Exception:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.exception("document_processing_failed", filename=filename)

            return ProcessedDocument(
                filename=filename,
                file_type=file_type,
                chunks=[],
                page_count=0,
                image_count=0,
                total_characters=0,
                processing_time_ms=processing_time,
                success=False,
                error="Internal error",
            )

    async def process_zip(
        self,
        zip_content: bytes,
        base_document_id: str,
        collection_name: str,
        course_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BatchProcessResult:
        """
        Process a ZIP archive containing multiple documents.

        OPTIMIZED VERSION:
        - Extracts to temp directory (saves memory)
        - Processes files in parallel batches
        - Streams file content instead of loading all at once
        - Collects garbage after processing large files

        Args:
            zip_content: ZIP file bytes
            base_document_id: Base document ID (will be suffixed for each file)
            collection_name: Vector store collection name
            course_id: Optional course ID
            metadata: Optional additional metadata

        Returns:
            BatchProcessResult with all processed documents
        """
        start_time = datetime.now()
        documents: List[ProcessedDocument] = []
        temp_dir = None

        try:
            # Create temporary directory for extraction (saves memory vs in-memory processing)
            temp_dir = tempfile.mkdtemp(prefix="kolabri_zip_")
            zip_path = os.path.join(temp_dir, "archive.zip")

            # Write ZIP to temp file first
            with open(zip_path, "wb") as f:
                f.write(zip_content)

            # Free the zip_content from memory
            del zip_content
            gc.collect()

            # Extract files
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                # Security: Sanitize namelist to prevent Path Traversal (Zip Slip)
                file_list = []
                for f in zip_ref.namelist():
                    if (
                        f.endswith("/")
                        or Path(f).name.startswith(".")
                        or f.startswith("__MACOSX")
                    ):
                        continue

                    # Normalize path and check if it tries to go outside current dir
                    safe_path = os.path.normpath(f)
                    if safe_path.startswith("..") or os.path.isabs(safe_path):
                        logger.warning("skipping_unsafe_zip_path", path=f)
                        continue

                    if (
                        Path(f).suffix.lower() in self.SUPPORTED_EXTENSIONS
                        and Path(f).suffix.lower() != ".zip"
                    ):
                        file_list.append(f)

                logger.info("zip_extraction_started", total_files=len(file_list))
                zip_ref.extractall(extract_dir, members=file_list)

            # Remove the zip file to free space
            os.remove(zip_path)
            gc.collect()

            # Process files sequentially to keep peak memory low
            for global_index, file_path in enumerate(file_list):
                filename = Path(file_path).name
                full_path = os.path.join(extract_dir, file_path)

                if not os.path.exists(full_path):
                    continue

                logger.info(
                    "zip_processing_file",
                    filename=filename,
                    index=global_index + 1,
                    total=len(file_list),
                )

                result = await self._process_file_from_path(
                    file_path=full_path,
                    filename=filename,
                    document_id=f"{base_document_id}_{global_index}_{hashlib.md5(filename.encode()).hexdigest()[:8]}",
                    collection_name=collection_name,
                    course_id=course_id,
                    metadata={
                        **(metadata or {}),
                        "zip_source": True,
                        "original_path": file_path,
                    },
                )
                documents.append(result)

                # Garbage collect after each file to free decompressed data
                gc.collect()

            processing_time = (datetime.now() - start_time).total_seconds() * 1000

            successful = [d for d in documents if d.success]
            failed = [d for d in documents if not d.success]

            logger.info(
                "zip_processing_complete",
                total=len(documents),
                successful=len(successful),
                failed=len(failed),
                total_chunks=sum(len(d.chunks) for d in successful),
                processing_time_ms=processing_time,
            )

            return BatchProcessResult(
                total_files=len(documents),
                successful_files=len(successful),
                failed_files=len(failed),
                total_chunks=sum(len(d.chunks) for d in successful),
                documents=documents,
                processing_time_ms=processing_time,
            )

        except zipfile.BadZipFile:
            return BatchProcessResult(
                total_files=0,
                successful_files=0,
                failed_files=1,
                total_chunks=0,
                documents=[],
                processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
            )
        finally:
            # Clean up temp directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    logger.exception("temp_cleanup_failed")
            gc.collect()

    async def _process_file_from_path(
        self,
        file_path: str,
        filename: str,
        document_id: str,
        collection_name: str,
        course_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProcessedDocument:
        """
        Process a file from disk path (memory-efficient for large files).
        Passes file_path directly to process_file to avoid loading into RAM.
        """
        try:
            result = await self.process_file(
                file_content=None,
                filename=filename,
                document_id=document_id,
                collection_name=collection_name,
                course_id=course_id,
                metadata=metadata,
                file_path=file_path,
            )
            return result

        except Exception:
            logger.exception("file_from_path_failed", path=file_path)
            return ProcessedDocument(
                filename=filename,
                file_type="unknown",
                chunks=[],
                page_count=0,
                image_count=0,
                total_characters=0,
                processing_time_ms=0,
                success=False,
                error="Internal error",
            )
        finally:
            gc.collect()

    async def _process_pdf(
        self,
        content: Optional[bytes],
        filename: str,
        document_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        file_path: Optional[str] = None,
    ) -> ProcessedDocument:
        from app.services.document_processing.text_extraction import process_pdf

        return await process_pdf(
            content,
            filename,
            document_id,
            metadata,
            file_path,
            ocr_available=self.ocr_available,
            vision_available=self.vision_available,
            min_text_length_for_ocr=self.MIN_TEXT_LENGTH_FOR_OCR,
            max_images_per_page=self.MAX_IMAGES_PER_PAGE,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            min_image_width=settings.MIN_IMAGE_WIDTH,
            min_image_height=settings.MIN_IMAGE_HEIGHT,
            ocr_fn=self._run_page_ocr,
            caption_fn=self._generate_image_caption,
            _fitz=fitz,
        )

    async def _process_docx(
        self,
        content: bytes,
        filename: str,
        document_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProcessedDocument:
        from app.services.document_processing.text_extraction import process_docx

        return await process_docx(
            content,
            filename,
            document_id,
            metadata,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            ocr_available=self.ocr_available,
            ocr_fn=self._run_ocr_optimized,
            _DocxDocument=DocxDocument,
            _extract_images_fn=self._extract_images_from_docx,
        )

    async def _process_pptx(
        self,
        content: bytes,
        filename: str,
        document_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProcessedDocument:
        from app.services.document_processing.text_extraction import process_pptx

        return await process_pptx(
            content,
            filename,
            document_id,
            metadata,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            ocr_available=self.ocr_available,
            ocr_fn=self._run_ocr_optimized,
            _Presentation=Presentation,
        )

    async def _process_text(
        self,
        content: bytes,
        filename: str,
        document_id: str,
        file_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProcessedDocument:
        from app.services.document_processing.text_extraction import process_text

        return await process_text(
            content,
            filename,
            document_id,
            file_type,
            metadata,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

    async def _process_image(
        self,
        content: bytes,
        filename: str,
        document_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProcessedDocument:
        from app.services.document_processing import image_extraction

        return await image_extraction.process_image(
            content=content,
            filename=filename,
            document_id=document_id,
            metadata=metadata,
            vision_available=self.vision_available,
            caption_fn=self._generate_image_caption,
            create_chunks_fn=self._create_chunks,
        )

    async def _generate_image_caption(self, image: Image.Image) -> str:
        from app.services.document_processing import image_extraction

        return await image_extraction.generate_image_caption(
            image,
            vision_client=self._vision_client,
        )

    def _extract_images_from_docx(self, doc_content: bytes):
        from app.services.document_processing.text_extraction import (
            _extract_images_from_docx,
        )

        yield from _extract_images_from_docx(doc_content)

    async def _process_extracted_images(self, images: List[Image.Image]) -> str:
        combined_text = []
        for img in images:
            try:
                text = await self._run_ocr_optimized(img)
                if text:
                    combined_text.append(f"[IMAGE_OCR]: {text}")
            finally:
                img.close()
                del img
                gc.collect()
        return "\n\n".join(combined_text)

    def _initialize_ocr_engine(self) -> None:
        if self._ocr_engine is not None or not OCR_AVAILABLE:
            return
        from app.services.document_processing import image_extraction

        engine = image_extraction.initialize_ocr_engine()
        if engine is None:
            self.ocr_available = False
        self._ocr_engine = engine

    async def _run_ocr(self, image: Image.Image) -> str:
        return await self._run_ocr_optimized(image)

    def _run_paddle_ocr(self, image: Image.Image) -> str:
        if not self._ocr_engine:
            self._initialize_ocr_engine()
        from app.services.document_processing import image_extraction

        return image_extraction.run_paddle_ocr(image, self._ocr_engine)

    async def _run_ocr_optimized(self, image: Image.Image) -> str:
        from app.services.document_processing import image_extraction

        return await image_extraction.run_ocr_optimized(
            image,
            ocr_available=self.ocr_available,
            ocr_engine=self._ocr_engine,
            max_image_size=self.MAX_IMAGE_SIZE,
        )

    async def _run_page_ocr(self, page: fitz.Page) -> str:
        from app.services.document_processing import image_extraction

        return await image_extraction.run_page_ocr(
            page,
            ocr_available=self.ocr_available,
            ocr_engine=self._ocr_engine,
            max_image_size=self.MAX_IMAGE_SIZE,
        )

    def _create_chunks(
        self,
        text: str,
        document_id: str,
        filename: str,
        page_number: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[ProcessedChunk]:
        """Create overlapping chunks from text."""
        from app.services.document_processing import create_chunks as _create

        specs = _create(
            text=text,
            document_id=document_id,
            filename=filename,
            page_number=page_number,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            metadata=metadata,
        )
        return [
            ProcessedChunk(text=s.text, metadata=s.metadata, chunk_id=s.chunk_id)
            for s in specs
        ]

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        from app.services.document_processing import clean_text

        return clean_text(text)

    async def _store_chunks(
        self,
        chunks: List[ProcessedChunk],
        collection_name: str,
        batch_size: int = 100,
    ) -> None:
        """Store chunks in vector store with batching to limit memory usage."""
        if not chunks:
            return

        vector_store = get_vector_store()

        documents = [chunk.text for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]
        ids = [chunk.chunk_id for chunk in chunks]

        total = len(documents)
        for i in range(0, total, batch_size):
            batch_docs = documents[i : i + batch_size]
            batch_meta = metadatas[i : i + batch_size]
            batch_ids = ids[i : i + batch_size]

            await vector_store.add_documents(
                documents=batch_docs,
                metadatas=batch_meta,
                ids=batch_ids,
                collection_name=collection_name,
            )

            logger.info(
                "chunks_batch_stored",
                collection=collection_name,
                batch=f"{i // batch_size + 1}/{(total + batch_size - 1) // batch_size}",
                count=len(batch_docs),
            )

        logger.info("chunks_stored", collection=collection_name, count=total)


# Singleton instance
_document_processor: Optional[DocumentProcessor] = None


def get_document_processor(
    provider_context: Optional[Dict[str, Any]] = None,
) -> DocumentProcessor:
    if provider_context is not None:
        return DocumentProcessor(provider_context=provider_context)

    global _document_processor
    if _document_processor is None:
        _document_processor = DocumentProcessor()
    return _document_processor
