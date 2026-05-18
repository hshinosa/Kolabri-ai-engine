"""
Document ingest, batch ingest & delete endpoints.
"""

import gc
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from app.api.schemas import BatchUploadResponse, IngestResponse
from app.core.config import settings
from app.core.logging import get_logger
from app.services.document_processor import get_document_processor
from app.services.vector_store import get_vector_store

logger = get_logger(__name__)

router = APIRouter()

COURSE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_course_id(course_id: str) -> str:
    if not course_id or not COURSE_ID_PATTERN.match(course_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid course ID format. Only alphanumeric characters, underscores, and hyphens are allowed.",
        )
    return course_id


async def _process_ingest_background(
    tmp_path: str,
    original_filename: str,
    course_id: str,
    file_id: str,
) -> None:
    start_time = datetime.now()
    try:
        doc_processor = get_document_processor()
        document_id = file_id
        collection_name = f"course_{course_id}"

        result = await doc_processor.process_file(
            file_path=tmp_path,
            filename=original_filename,
            document_id=document_id,
            collection_name=collection_name,
            course_id=course_id,
            metadata={
                "course_id": course_id,
                "file_id": file_id,
                "original_filename": original_filename,
                "upload_time": datetime.now().isoformat(),
            },
        )

        processing_time = (datetime.now() - start_time).total_seconds() * 1000

        if result.success:
            logger.info(
                "document_ingested",
                file_id=file_id,
                course_id=course_id,
                filename=original_filename,
                file_type=result.file_type,
                chunks=len(result.chunks),
                pages=result.page_count,
                images=result.image_count,
                processing_time_ms=processing_time,
            )
        else:
            logger.error(
                "document_ingest_failed_background",
                file_id=file_id,
                filename=original_filename,
                error=result.error,
            )
    except Exception:
        logger.exception(
            "document_ingest_failed",
            file_id=file_id,
            filename=original_filename,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        gc.collect()


async def _process_batch_file_background(
    tmp_path: str,
    original_filename: str,
    course_id: str,
    document_id: str,
    batch_index: int,
    extract_images: bool,
    perform_ocr: bool,
) -> None:
    try:
        doc_processor = get_document_processor()
        collection_name = f"course_{course_id}"

        result = await doc_processor.process_file(
            file_path=tmp_path,
            filename=original_filename,
            document_id=document_id,
            collection_name=collection_name,
            course_id=course_id,
            metadata={
                "course_id": course_id,
                "batch_index": batch_index,
                "original_filename": original_filename,
                "upload_time": datetime.now().isoformat(),
                "extract_images": extract_images,
                "perform_ocr": perform_ocr,
            },
        )

        if result.success:
            logger.info(
                "batch_file_ingested",
                document_id=document_id,
                course_id=course_id,
                filename=original_filename,
                chunks=len(result.chunks) if result.chunks else 0,
            )
        else:
            logger.error(
                "batch_file_ingest_failed_background",
                document_id=document_id,
                filename=original_filename,
                error=result.error,
            )
    except Exception:
        logger.exception(
            "batch_file_ingest_failed",
            document_id=document_id,
            filename=original_filename,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        gc.collect()


@router.post(
    "/ingest",
    response_model=IngestResponse,
    tags=["Core-API Integration"],
    summary="Ingest document into vector store (supports PDF, DOCX, PPTX, TXT, ZIP)",
)
async def ingest_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    course_id: str = Form(...),
    file_id: str = Form(...),
):
    validate_course_id(course_id)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    ext = Path(file.filename).suffix.lower()
    supported_extensions = [
        ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".txt", ".md", ".zip",
    ]

    if ext not in supported_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Supported: {', '.join(supported_extensions)}",
        )

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext)
    try:
        file_size = 0
        max_size = (
            (settings.MAX_ZIP_SIZE_MB if ext == ".zip" else settings.MAX_UPLOAD_SIZE_MB)
            * 1024
            * 1024
        )

        with os.fdopen(tmp_fd, "wb") as tmp_file:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > max_size:
                    tmp_file.close()
                    os.unlink(tmp_path)
                    raise HTTPException(
                        status_code=400, detail="File size exceeds limit"
                    )
                tmp_file.write(chunk)
    except HTTPException:
        raise
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    original_filename = file.filename
    background_tasks.add_task(
        _process_ingest_background,
        tmp_path=tmp_path,
        original_filename=original_filename,
        course_id=course_id,
        file_id=file_id,
    )

    logger.info(
        "document_ingest_scheduled",
        file_id=file_id,
        course_id=course_id,
        filename=original_filename,
        file_size=file_size,
    )

    return IngestResponse(
        success=True,
        message="Dokumen sedang diproses di latar belakang",
        file_id=file_id,
        document_id=file_id,
        chunks_created=0,
        page_count=0,
        image_count=0,
        file_type=ext.lstrip("."),
        processing_time_ms=0,
    )


@router.post(
    "/ingest/batch",
    response_model=BatchUploadResponse,
    tags=["Core-API Integration"],
    summary="Batch ingest multiple documents or ZIP archive",
)
async def ingest_batch(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    course_id: str = Form(...),
    extract_images: bool = Form(True),
    perform_ocr: bool = Form(False),
):
    saved_files: list[dict] = []

    for i, file in enumerate(files):
        if not file.filename:
            continue

        ext = Path(file.filename).suffix.lower()
        suffix = ext if ext else ".bin"

        try:
            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix=suffix, prefix="batch_"
            )
            contents = await file.read()
            tmp.write(contents)
            tmp.close()
            del contents
            gc.collect()

            document_id = f"{course_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{i}"

            saved_files.append(
                {
                    "tmp_path": tmp.name,
                    "filename": file.filename,
                    "document_id": document_id,
                    "index": i,
                }
            )
        except Exception:
            logger.exception("batch_file_save_failed", filename=file.filename)

    if not saved_files:
        raise HTTPException(status_code=400, detail="No valid files provided")

    for entry in saved_files:
        background_tasks.add_task(
            _process_batch_file_background,
            tmp_path=entry["tmp_path"],
            original_filename=entry["filename"],
            course_id=course_id,
            document_id=entry["document_id"],
            batch_index=entry["index"],
            extract_images=extract_images,
            perform_ocr=perform_ocr,
        )

    return BatchUploadResponse(
        success=True,
        message=f"{len(saved_files)} dokumen sedang diproses di latar belakang",
        total_files=len(saved_files),
        successful_files=0,
        failed_files=0,
        total_chunks=0,
        documents=[],
        processing_time_ms=0,
    )


@router.delete(
    "/documents/{document_id}",
    tags=["Documents"],
    summary="Delete a document from the vector store",
)
async def delete_document(
    document_id: str,
    collection_name: str = Query(None, description="Collection to delete from"),
):
    try:
        vector_store = get_vector_store()
        target_collection = collection_name or "default"

        await vector_store.delete_documents(
            where={"document_id": document_id},
            collection_name=target_collection,
        )

        logger.info("document_deleted", document_id=document_id, collection=target_collection)

        return JSONResponse(
            content={
                "success": True,
                "message": f"Document {document_id} deleted from {target_collection}",
            }
        )

    except Exception:
        logger.exception("document_delete_failed")
        raise
