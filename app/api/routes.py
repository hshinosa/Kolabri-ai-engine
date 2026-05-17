"""
API Routes - MVP Phase 1-1.5
Kolabri AI Engine

FastAPI router with all API endpoints.
"""

import gc
import os
import re
import uuid
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from fastapi import (
    APIRouter,
    BackgroundTasks,
    UploadFile,
    File,
    Form,
    HTTPException,
    Query,
)
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.core.config import settings
from app.core.logging import get_logger
from app.core.prompt_styles import PERSONAL_CHAT_STYLE
from app.services.document_processor import get_document_processor

# [PRIORITY 1] Optimized services dengan connection pooling & caching
from app.services.llm import get_llm_service
from app.services.rag import get_rag_pipeline

# [PRIORITY 2] Vector store caching & MongoDB pooling
from app.services.vector_store import get_vector_store
from app.services.mongodb_logger import get_mongo_logger
from app.core.cache_analyzer import get_cache_analyzer

# [PRIORITY 3] Batching & Circuit Breaker
from app.services.batch_llm import get_batch_llm_service
from app.services.circuit_breaker import get_llm_circuit_breaker
from app.services.monitoring import get_monitor
from app.services.reranker import get_reranker

from app.services.intervention import get_intervention_service, InterventionType
from app.services.orchestration import get_orchestrator
from app.services.nlp_analytics import get_engagement_analyzer
from app.utils.logger import get_process_mining_logger
from app.api.schemas import (
    HealthResponse,
    PDFUploadResponse,
    DocumentProcessResult,
    BatchUploadResponse,
    IngestResponse,
    DocumentListResponse,
    DocumentInfo,
    QueryRequest,
    QueryResponse,
    SourceInfo,
    AskRequest,
    AskResponse,
    InterventionRequest,
    InterventionResponse,
    SummaryRequest,
    SummaryResponse,
    PromptRequest,
    PromptResponse,
    CreateCollectionRequest,
    CollectionResponse,
    CollectionListResponse,
    ErrorResponse,
    OrchestrationRequest,
    OrchestrationResponse,
    GroupAnalyticsRequest,
    GroupAnalyticsResponse,
    EngagementAnalysisRequest,
    EngagementAnalysisResponse,
    ProcessMiningExportResponse,
    GuardrailCheckRequest,
    GuardrailCheckResponse,
    PersonalChatRequest,
    PersonalChatResponse,
)
from app.core.guardrails import get_guardrails, GuardrailAction
from app.services.export_service import get_export_service
from app.services.efficiency_guard import get_efficiency_guard

# [PRIORITY 1] Batch routes untuk high throughput
from app.api.batch_routes import router as batch_router

logger = get_logger(__name__)

# Router for API endpoints
router = APIRouter()

PERSONAL_CHAT_SYSTEM_PROMPT = (
    "Kamu adalah Kolabri AI, asisten belajar cerdas untuk mahasiswa. "
    "Bantu mahasiswa memahami materi, menjawab pertanyaan akademik maupun pertanyaan personal ringan dengan penjelasan yang jelas, akurat, suportif, dan edukatif. "
    "Jawab dalam Bahasa Indonesia kecuali diminta sebaliknya. "
    + PERSONAL_CHAT_STYLE
)

# Course ID validation pattern (alphanumeric, underscore, hyphen only)
COURSE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')


def validate_course_id(course_id: str) -> str:
    """
    Validate course_id format to prevent injection attacks.
    
    Args:
        course_id: The course ID to validate
        
    Returns:
        The validated course_id
        
    Raises:
        HTTPException: If course_id contains invalid characters
    """
    if not course_id or not COURSE_ID_PATTERN.match(course_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid course ID format. Only alphanumeric characters, underscores, and hyphens are allowed."
        )
    return course_id

# Include batch routes
router.include_router(batch_router, prefix="/ask", tags=["Batch Processing"])


# ============== Core-API Integration Endpoints ==============
# These endpoints are called by Core-API (Express.js backend)


@router.post(
    "/ask",
    response_model=AskResponse,
    tags=["Core-API Integration"],
    summary="Answer question using RAG (for chat @AI mention)",
)
async def ask_question(request: AskRequest):
    """
    Answer a question using RAG - called when user mentions @AI in chat.
    """
    try:
        # ✅ SEC: KOL-147 - Validate course_id format
        validate_course_id(request.course_id)
        
        rag_pipeline = get_rag_pipeline()

        # Use course-specific collection
        collection_name = f"course_{request.course_id}"

        result = await rag_pipeline.query(
            query=request.query, collection_name=collection_name, n_results=5
        )

        if result.success:
            # Format answer with sources if available
            answer = result.answer
            if result.sources:
                sources_text = "\n\n📚 *Sumber:*\n"
                for i, src in enumerate(result.sources[:3], 1):
                    source_name = src.get("source", "Dokumen")
                    page = src.get("page")
                    if page:
                        sources_text += f"{i}. {source_name} (hal. {page})\n"
                    else:
                        sources_text += f"{i}. {source_name}\n"
                answer += sources_text

            return AskResponse(answer=answer, success=True)
        else:
            return AskResponse(
                answer="Maaf, saya tidak bisa menemukan jawaban untuk pertanyaan tersebut dalam materi kuliah.",
                success=False,
                error=result.error,
            )

    except Exception as e:
        logger.error("ask_question_failed", query=request.query[:100], error=str(e))
        return AskResponse(
            answer="Maaf, terjadi kesalahan saat memproses pertanyaan. Silakan coba lagi.",
            success=False,
            error=str(e),
        )


@router.post(
    "/chat/personal",
    response_model=PersonalChatResponse,
    tags=["Core-API Integration"],
    summary="Personal AI chat (multi-turn, no RAG)",
)
async def personal_chat(request: PersonalChatRequest):
    try:
        llm = get_llm_service()

        messages = [
            {"role": "system", "content": PERSONAL_CHAT_SYSTEM_PROMPT},
        ]

        for msg in request.history[-20:]:
            messages.append({"role": msg.role, "content": msg.content})

        messages.append({"role": "user", "content": request.message})

        response = await llm.client.chat.completions.create(
            model=llm.model,
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
        )

        reply = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else 0

        return PersonalChatResponse(reply=reply, success=True, tokens_used=tokens)

    except Exception as e:
        logger.error("personal_chat_failed", error=str(e))
        return PersonalChatResponse(
            reply="Maaf, terjadi kesalahan. Silakan coba lagi.",
            success=False,
            error=str(e),
        )


@router.post(
    "/chat/personal/stream",
    tags=["Core-API Integration"],
    summary="Personal AI chat with SSE streaming",
)
async def personal_chat_stream(request: PersonalChatRequest):
    import json as _json

    llm = get_llm_service()

    messages = [
        {"role": "system", "content": PERSONAL_CHAT_SYSTEM_PROMPT},
    ]

    for msg in request.history[-20:]:
        messages.append({"role": msg.role, "content": msg.content})

    messages.append({"role": "user", "content": request.message})

    async def event_generator():
        try:
            stream = await llm.client.chat.completions.create(
                model=llm.model,
                messages=messages,
                temperature=0.7,
                max_tokens=2048,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield f"data: {_json.dumps({'content': delta.content})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error("personal_chat_stream_failed", error=str(e))
            yield f"data: {_json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
    """
    Ingest a document into the vector store (background processing).
    """
    # ✅ SEC: KOL-147 - Validate course_id format
    validate_course_id(course_id)
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Get file extension
    ext = Path(file.filename).suffix.lower()
    supported_extensions = [
        ".pdf",
        ".docx",
        ".doc",
        ".pptx",
        ".ppt",
        ".txt",
        ".md",
        ".zip",
    ]

    if ext not in supported_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Supported: {', '.join(supported_extensions)}",
        )

    # Save uploaded file to a temporary location instead of reading into RAM
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext)
    try:
        # Stream file content to disk in chunks to avoid loading entire file into RAM
        file_size = 0
        max_size = (
            (settings.MAX_ZIP_SIZE_MB if ext == ".zip" else settings.MAX_UPLOAD_SIZE_MB)
            * 1024
            * 1024
        )

        with os.fdopen(tmp_fd, "wb") as tmp_file:
            while True:
                chunk = await file.read(1024 * 1024)  # Read 1MB at a time
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
    except Exception as e:
        # Clean up temp file on error during write
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise HTTPException(
            status_code=500, detail=f"Failed to save uploaded file: {str(e)}"
        )

    # Schedule background processing
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


async def _process_ingest_background(
    tmp_path: str,
    original_filename: str,
    course_id: str,
    file_id: str,
) -> None:
    """Background task to process a document from a temp file path."""
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
    except Exception as e:
        logger.error(
            "document_ingest_failed",
            file_id=file_id,
            filename=original_filename,
            error=str(e),
        )
    finally:
        # Always clean up temp file
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        gc.collect()


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
    """
    Batch ingest multiple documents at once.

    Accepts multiple files or a single ZIP archive containing documents.
    Files are saved to temporary paths and processed in the background.

    Args:
        background_tasks: FastAPI BackgroundTasks for async processing
        files: List of document files to process
        course_id: Course ID to associate documents with

    Returns:
        Acknowledgement with file count — processing runs in background
    """
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
        except Exception as e:
            logger.error("batch_file_save_failed", filename=file.filename, error=str(e))

    if not saved_files:
        raise HTTPException(status_code=400, detail="No valid files provided")

    # Schedule background processing for each file
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


async def _process_batch_file_background(
    tmp_path: str,
    original_filename: str,
    course_id: str,
    document_id: str,
    batch_index: int,
    extract_images: bool,
    perform_ocr: bool,
) -> None:
    """Background task to process a single file from a batch upload."""
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
    except Exception as e:
        logger.error(
            "batch_file_ingest_failed",
            document_id=document_id,
            filename=original_filename,
            error=str(e),
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        gc.collect()


# ============== Health Check ==============


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Health check endpoint",
)
async def health_check():
    """
    Check the health status of the AI Engine.

    Returns status of all dependent services.
    """
    services = {
        "vector_store": False,
        "llm": False,
    }

    # Check vector store
    try:
        vector_store = get_vector_store()
        await vector_store._ensure_collection("health_check")
        services["vector_store"] = True
    except Exception as e:
        logger.warning("health_check_vector_store_failed", error=str(e))

    # Check LLM (just verify it's initialized)
    try:
        from app.services.llm import get_llm_service

        llm = get_llm_service()
        services["llm"] = llm.model is not None
    except Exception as e:
        logger.warning("health_check_llm_failed", error=str(e))

    overall_status = "healthy" if all(services.values()) else "degraded"

    reranker = get_reranker()
    return HealthResponse(
        status=overall_status,
        version=settings.VERSION,
        timestamp=datetime.now(),
        services=services,
        reranker_enabled=reranker.enabled,
    )


@router.post(
    "/analytics/engagement",
    response_model=EngagementAnalysisResponse,
    tags=["Analytics"],
    summary="Analyze text engagement metrics (Core-API Proxy)",
)
async def analyze_engagement(request: EngagementAnalysisRequest):
    """
    Analyze text for engagement metrics (Lexical, HOT, etc).
    Called by Core-API for real-time analysis.
    """
    try:
        analyzer = get_engagement_analyzer()
        analysis = analyzer.analyze_interaction(request.text)

        return EngagementAnalysisResponse(
            success=True,
            lexical_variety=analysis.lexical_variety,
            engagement_type=analysis.engagement_type.value,
            is_higher_order=analysis.is_higher_order,
            hot_indicators=analysis.hot_indicators,
            word_count=len(request.text.split()),
            unique_words=len(set(request.text.lower().split())),
            confidence=1.0,  # Simplified
        )
    except Exception as e:
        logger.error("engagement_analysis_failed", error=str(e))
        return EngagementAnalysisResponse(
            success=False,
            error=str(e),
            lexical_variety=0,
            engagement_type="unknown",
            is_higher_order=False,
            hot_indicators=[],
            word_count=0,
            unique_words=0,
            confidence=0,
        )


@router.get(
    "/analytics/dashboard/group/{group_id}",
    tags=["Analytics"],
    summary="Get dashboard data for a GROUP (Collaboration & Dynamics)",
)
async def get_group_dashboard(group_id: str):
    """
    Get metrics focused on Group Collaboration.
    - Gini Participation
    - Group Plan vs Reality
    - Collective Anomalies
    """
    try:
        orchestrator = get_orchestrator()
        data = await orchestrator.get_group_dashboard_data(group_id)
        return JSONResponse(content=data)
    except Exception as e:
        logger.error("group_dashboard_api_failed", group_id=group_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/analytics/dashboard/individual/{user_id}",
    tags=["Analytics"],
    summary="Get dashboard data for an INDIVIDUAL student",
)
async def get_individual_dashboard(user_id: str):
    """
    Get metrics focused on Personal Progress.
    - Individual message quality
    - Personal HOT trends
    - Technical topics mastered
    """
    try:
        orchestrator = get_orchestrator()
        data = await orchestrator.get_individual_dashboard_data(user_id)
        return JSONResponse(content=data)
    except Exception as e:
        logger.error("individual_dashboard_api_failed", user_id=user_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/analytics/dashboard/{group_id}",
    tags=["Analytics"],
    summary="Get unified dashboard data (Legacy - redirects to group)",
)
async def get_dashboard_data_legacy(group_id: str):
    return await get_group_dashboard(group_id)


# ============== Activity Data CSV Export ==============
# New endpoint for exporting activity data for manual assessment


@router.get(
    "/export/activity/group/{group_id}",
    tags=["Analytics"],
    summary="Export group activity data to CSV (Student Breakdown)",
)
async def export_group_activity_csv(group_id: str):
    """
    Export group activity data with per-student detailed breakdown.
    Focuses on what each student did across all chat spaces (sessions) in their group.
    """
    try:
        export_service = get_export_service()
        csv_data = await export_service.export_group_activity_detailed(group_id)

        filename = f"student_breakdown_{group_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        logger.error("csv_export_failed", group_id=group_id, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to export activity data: {str(e)}"
        )


@router.get(
    "/export/activity/chat-space/{chat_space_id}",
    tags=["Analytics"],
    summary="Export chat space activity data to CSV",
)
async def export_chat_space_activity_csv(
    chat_space_id: str,
    include_detailed: bool = Query(True, description="Include detailed metrics"),
):
    """
    Export chat space activity data to CSV format.

    Similar to group export but for specific chat space (session).

    Args:
        chat_space_id: The chat space ID to export data for
        include_detailed: Whether to include detailed engagement metrics

    Returns:
        CSV file download
    """
    try:
        export_service = get_export_service()

        csv_data = await export_service.export_chat_space_activity(
            chat_space_id=chat_space_id, include_detailed=include_detailed
        )

        filename = f"activity_session_{chat_space_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        logger.info(
            "activity_csv_exported",
            chat_space_id=chat_space_id,
            size_bytes=len(csv_data),
            detailed=include_detailed,
        )

        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        logger.error("csv_export_failed", chat_space_id=chat_space_id, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to export activity data: {str(e)}"
        )


@router.get(
    "/export/process-mining/case/{case_id}",
    tags=["Analytics"],
    summary="Export raw event logs to CSV for Process Mining (XES compatible)",
)
async def export_process_mining_csv(case_id: str):
    """
    Export raw event logs to CSV format compatible with Process Mining tools.

    The schema follows Proposal TA requirements:
    CaseID, Activity, Timestamp, Resource, Lifecycle, original_text, etc.

    Args:
        case_id: The CaseID to export (e.g., group_123_session_5)

    Returns:
        CSV file download
    """
    try:
        from app.services.mongodb_logger import get_mongo_logger

        mongo_logger = get_mongo_logger()

        csv_data = await mongo_logger.export_to_csv(case_id=case_id)

        filename = (
            f"process_mining_{case_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )

        logger.info(
            "process_mining_csv_exported", case_id=case_id, size_bytes=len(csv_data)
        )

        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        logger.error("process_mining_export_failed", case_id=case_id, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to export process mining data: {str(e)}"
        )


# ============== SMART Goal Validation Endpoints ==============
# New endpoints for SMART goal validation and refinement


@router.post(
    "/goals/validate",
    tags=["Goals"],
    summary="Validate a learning goal against SMART criteria",
)
async def validate_goal(
    goal_text: str = Form(...), user_id: str = Form(...), chat_space_id: str = Form(...)
):
    """
    Validate a learning goal against SMART criteria.

    This endpoint analyzes a student's goal statement and checks if it meets
    the SMART criteria: Specific, Measurable, Achievable, Relevant, Time-bound.

    Args:
        goal_text: The goal statement to validate
        user_id: ID of the user setting the goal
        chat_space_id: ID of the chat space

    Returns:
        Validation result with score, feedback, and suggestions
    """
    try:
        orchestrator = get_orchestrator()

        result = await orchestrator.validate_goal(
            goal_text=goal_text, user_id=user_id, chat_space_id=chat_space_id
        )

        logger.info(
            "goal_validation_api",
            user_id=user_id,
            chat_space_id=chat_space_id,
            is_valid=result.get("is_valid"),
            score=result.get("score"),
        )

        return JSONResponse(content=result)

    except Exception as e:
        logger.error("goal_validation_api_failed", error=str(e), user_id=user_id)
        raise HTTPException(
            status_code=500, detail=f"Failed to validate goal: {str(e)}"
        )


@router.post(
    "/goals/refine",
    tags=["Goals"],
    summary="Get Socratic questioning hints to improve SMART goal",
)
async def get_goal_refinement(
    current_goal: str = Form(...),
    missing_criteria: str = Form(...),  # JSON string of list
):
    """
    Get Socratic questioning hints to help student improve their SMART goal.

    This endpoint uses the LLM to generate helpful hints that guide students
    to improve their goal without giving direct answers.

    Args:
        current_goal: The student's current goal statement
        missing_criteria: JSON string of missing SMART criteria

    Returns:
        Refinement suggestion from LLM
    """
    try:
        import json

        missing_list = json.loads(missing_criteria)

        orchestrator = get_orchestrator()

        result = await orchestrator.get_goal_refinement(
            current_goal=current_goal, missing_criteria=missing_list
        )

        logger.info(
            "goal_refinement_api",
            current_goal=current_goal[:50],
            success=result.get("success"),
        )

        return JSONResponse(content=result)

    except json.JSONDecodeError as e:
        logger.error("goal_refinement_json_error", error=str(e))
        raise HTTPException(
            status_code=400, detail="Invalid JSON format for missing_criteria"
        )
    except Exception as e:
        logger.error("goal_refinement_api_failed", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get refinement: {str(e)}"
        )


# ============== Logic Listener Endpoints ==============
# New endpoints for real-time group monitoring and intervention


@router.get(
    "/groups/{group_id}/status",
    tags=["Groups"],
    summary="Check group status using Logic Listener",
)
async def check_group_status(
    group_id: str, topic: Optional[str] = Query(None, description="Discussion topic")
):
    """
    Check group status using Logic Listener for real-time monitoring.

    This endpoint analyzes group dynamics and detects:
    - Off-topic discussions
    - Silence periods
    - Participation inequity

    Args:
        group_id: ID of the group to check
        topic: Optional discussion topic

    Returns:
        Group status with intervention triggers
    """
    try:
        orchestrator = get_orchestrator()

        result = await orchestrator.check_group_status(group_id=group_id, topic=topic)

        logger.info(
            "group_status_check_api",
            group_id=group_id,
            should_intervene=result.get("should_intervene"),
            interventions_count=len(result.get("interventions", [])),
        )

        return JSONResponse(content=result)

    except Exception as e:
        logger.error("group_status_check_api_failed", error=str(e), group_id=group_id)
        raise HTTPException(
            status_code=500, detail=f"Failed to check group status: {str(e)}"
        )


@router.post(
    "/groups/{group_id}/track-participation",
    tags=["Groups"],
    summary="Track user participation for Logic Listener",
)
async def track_participation(group_id: str, user_id: str = Form(...)):
    """
    Track user participation for Logic Listener.

    This endpoint records when a user sends a message, which is used
    to calculate participation equity and detect silent members.

    Args:
        group_id: ID of the group
        user_id: ID of the user

    Returns:
        Tracking result
    """
    try:
        orchestrator = get_orchestrator()

        result = await orchestrator.track_participation(
            group_id=group_id, user_id=user_id
        )

        logger.info("participation_tracking_api", group_id=group_id, user_id=user_id)

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(
            "participation_tracking_api_failed",
            error=str(e),
            group_id=group_id,
            user_id=user_id,
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to track participation: {str(e)}"
        )


@router.post(
    "/groups/{group_id}/update-last-message",
    tags=["Groups"],
    summary="Update last message timestamp for Logic Listener",
)
async def update_last_message_time(group_id: str):
    """
    Update last message timestamp for Logic Listener.

    This endpoint updates the timestamp of the last message in a group,
    which is used to detect silence periods.

    Args:
        group_id: ID of the group

    Returns:
        Update result
    """
    try:
        orchestrator = get_orchestrator()

        result = await orchestrator.update_last_message_time(group_id=group_id)

        logger.info("last_message_time_update_api", group_id=group_id)

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(
            "last_message_time_update_api_failed", error=str(e), group_id=group_id
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to update last message time: {str(e)}"
        )


@router.post(
    "/groups/{group_id}/set-topic",
    tags=["Groups"],
    summary="Set the topic for a group for Logic Listener",
)
async def set_group_topic(group_id: str, topic: str = Form(...)):
    """
    Set the topic for a group for Logic Listener.

    This endpoint sets the discussion topic, which is used to detect
    off-topic discussions.

    Args:
        group_id: ID of the group
        topic: Discussion topic

    Returns:
        Set result
    """
    try:
        orchestrator = get_orchestrator()

        result = await orchestrator.set_group_topic(group_id=group_id, topic=topic)

        logger.info("group_topic_set_api", group_id=group_id, topic=topic)

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(
            "group_topic_set_api_failed", error=str(e), group_id=group_id, topic=topic
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to set group topic: {str(e)}"
        )


# ============== Efficiency Guard Endpoints ==============
# New endpoints for caching, rate limiting, and performance optimization


@router.get(
    "/efficiency/cache/statistics",
    tags=["Efficiency"],
    summary="Get cache performance statistics",
)
async def get_cache_statistics():
    """
    Get cache performance statistics.

    Returns information about cache hits, misses, hit rate, and cache size.
    """
    try:
        if not settings.ENABLE_EFFICIENCY_GUARD:
            return JSONResponse(
                content={"enabled": False, "message": "Efficiency Guard is disabled"}
            )

        efficiency_guard = get_efficiency_guard()
        stats = efficiency_guard.get_cache_statistics()

        logger.info(
            "cache_statistics_api",
            cache_hits=stats.get("cache_hits"),
            cache_misses=stats.get("cache_misses"),
            hit_rate=stats.get("hit_rate_percent"),
        )

        return JSONResponse(content={"enabled": True, **stats})

    except Exception as e:
        logger.error("cache_statistics_api_failed", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get cache statistics: {str(e)}"
        )


@router.get(
    "/efficiency/cache/clear", tags=["Efficiency"], summary="Clear all cached responses"
)
async def clear_cache():
    """
    Clear all cached responses.

    This endpoint removes all entries from the cache.
    """
    try:
        if not settings.ENABLE_EFFICIENCY_GUARD:
            return JSONResponse(
                content={"enabled": False, "message": "Efficiency Guard is disabled"}
            )

        efficiency_guard = get_efficiency_guard()
        efficiency_guard.clear_cache()

        logger.info("cache_cleared_api")

        return JSONResponse(
            content={"success": True, "message": "Cache cleared successfully"}
        )

    except Exception as e:
        logger.error("cache_clear_api_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@router.get(
    "/efficiency/statistics",
    tags=["Efficiency"],
    summary="Get comprehensive efficiency guard statistics",
)
async def get_efficiency_statistics():
    """
    Get comprehensive efficiency guard statistics.

    Returns detailed statistics about cache, rate limiting, and query patterns.
    """
    try:
        if not settings.ENABLE_EFFICIENCY_GUARD:
            return JSONResponse(
                content={"enabled": False, "message": "Efficiency Guard is disabled"}
            )

        efficiency_guard = get_efficiency_guard()
        stats = efficiency_guard.get_statistics()

        logger.info(
            "efficiency_statistics_api",
            total_requests=stats.get("rate_limit", {}).get("total_requests"),
            cache_hit_rate=stats.get("performance", {}).get("cache_hit_rate_percent"),
        )

        return JSONResponse(content={"enabled": True, **stats})

    except Exception as e:
        logger.error("efficiency_statistics_api_failed", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get efficiency statistics: {str(e)}"
        )


@router.get(
    "/efficiency/rate-limit/{identifier}",
    tags=["Efficiency"],
    summary="Get rate limit information for an identifier",
)
async def get_rate_limit_info(identifier: str):
    """
    Get rate limit information for a specific identifier.

    Args:
        identifier: Unique identifier for the requester (user_id, group_id, etc.)

    Returns:
        Rate limit information including remaining requests
    """
    try:
        if not settings.ENABLE_EFFICIENCY_GUARD:
            return JSONResponse(
                content={"enabled": False, "message": "Efficiency Guard is disabled"}
            )

        efficiency_guard = get_efficiency_guard()
        info = efficiency_guard.get_rate_limit_info(identifier)

        logger.info(
            "rate_limit_info_api",
            identifier=identifier,
            remaining=info.get("remaining_requests"),
            is_allowed=info.get("is_allowed"),
        )

        return JSONResponse(content={"enabled": True, **info})

    except Exception as e:
        logger.error("rate_limit_info_api_failed", error=str(e), identifier=identifier)
        raise HTTPException(
            status_code=500, detail=f"Failed to get rate limit info: {str(e)}"
        )


# ============================================================================
# [KOL-139] Performance Monitoring Endpoints
# ============================================================================

@router.get("/metrics", tags=["Monitoring"])
async def metrics():
    """
    Prometheus metrics endpoint.
    
    Returns all performance metrics in Prometheus format.
    """
    try:
        monitor = get_monitor()
        return Response(
            content=monitor.get_metrics(),
            media_type=monitor.get_content_type()
        )
    except Exception as e:
        logger.error("metrics_endpoint_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Metrics export failed: {str(e)}")


@router.get("/health/monitoring", tags=["Monitoring"])
async def get_monitoring_status():
    """Get monitoring service status and dashboard data."""
    try:
        monitor = get_monitor()
        return JSONResponse(content=monitor.get_dashboard_data())
    except Exception as e:
        logger.error("monitoring_status_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get monitoring status: {str(e)}")


# ============================================================================
# [KOL-135] Circuit Breaker Endpoints
# ============================================================================

@router.get("/health/circuit-breakers", tags=["Monitoring"])
async def get_circuit_breaker_status():
    """Get status of all circuit breakers."""
    try:
        llm_cb = get_llm_circuit_breaker()
        return JSONResponse(content={
            "llm_service": llm_cb.get_metrics()
        })
    except Exception as e:
        logger.error("circuit_breaker_status_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get circuit breaker status: {str(e)}")


# ============================================================================
# [KOL-136] RAG Re-Ranking Endpoints
# ============================================================================

@router.get("/health/reranker", tags=["Monitoring"])
async def get_reranker_status():
    """Get reranker health and metrics."""
    try:
        reranker = get_reranker()
        return JSONResponse(content=reranker.get_metrics())
    except Exception as e:
        logger.error("reranker_status_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get reranker status: {str(e)}")


@router.get(
    "/efficiency/high-frequency-queries",
    tags=["Efficiency"],
    summary="Get most frequently executed queries",
)
async def get_high_frequency_queries(
    limit: int = Query(10, description="Maximum number of queries to return"),
):
    """
    Get the most frequently executed queries.

    This endpoint helps identify which queries are executed most often,
    which can be useful for optimization and caching strategies.

    Args:
        limit: Maximum number of queries to return

    Returns:
        List of high-frequency queries with their counts
    """
    try:
        if not settings.ENABLE_EFFICIENCY_GUARD:
            return JSONResponse(
                content={"enabled": False, "message": "Efficiency Guard is disabled"}
            )

        efficiency_guard = get_efficiency_guard()
        queries = efficiency_guard.get_high_frequency_queries(limit=limit)

        logger.info("high_frequency_queries_api", limit=limit, count=len(queries))

        return JSONResponse(content={"enabled": True, "queries": queries})

    except Exception as e:
        logger.error("high_frequency_queries_api_failed", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to get high frequency queries: {str(e)}"
        )


# ============== Integration Endpoints (Core API <-> AI Engine) ==============
# These endpoints are called by Kolabri-core-api's AIEngineService


@router.post(
    "/chat",
    response_model=OrchestrationResponse,
    tags=["Orchestration"],
    summary="Orchestrated chat message processing",
    description="Process a student message through the full orchestration pipeline with NLP analysis, RAG, and intervention triggers.",
)
async def orchestrated_chat(request: OrchestrationRequest):
    """
    Main orchestrated chat endpoint called by Core API.
    Processes student messages through:
    - NLP engagement analysis
    - Policy-based RAG (FETCH/NO_FETCH)
    - Automatic intervention triggers
    - Process Mining event logging
    """
    try:
        orchestrator = get_orchestrator()
        result = await orchestrator.handle_message(
            user_id=request.user_id,
            group_id=request.group_id,
            message=request.message,
            topic=request.topic,
            collection_name=request.collection_name,
            course_id=request.course_id,
            chat_room_id=request.chat_room_id,
        )

        return OrchestrationResponse(
            success=result.success,
            bot_response=result.reply,
            system_intervention=result.intervention,
            intervention_type=result.intervention_type,
            action_taken=result.action_taken,
            should_notify_teacher=result.should_notify_teacher,
            quality_score=result.quality_score,
            meta=result.analytics,
            error=result.error,
        )

    except Exception as e:
        logger.error("orchestrated_chat_failed", error=str(e))
        return OrchestrationResponse(
            success=False,
            bot_response="Maaf, terjadi kesalahan sistem.",
            action_taken="ERROR",
            should_notify_teacher=False,
            error=str(e),
        )


@router.post(
    "/intervention/analyze",
    response_model=InterventionResponse,
    tags=["Intervention"],
    summary="Analyze chat for intervention needs",
    description="Analyze a group chat conversation and determine if AI intervention is needed.",
)
async def analyze_intervention(request: InterventionRequest):
    """
    Analyze chat messages and determine if pedagogical intervention is needed.
    Called by Core API's analyzeIntervention method.
    """
    try:
        intervention_service = get_intervention_service()

        # Convert schema messages to dict format expected by service
        messages_dicts = [
            {
                "sender": msg.sender,
                "content": msg.content,
                "timestamp": msg.timestamp,
                "sender_id": msg.sender_id,
            }
            for msg in request.messages
        ]

        result = await intervention_service.analyze_and_intervene(
            messages=messages_dicts,
            topic=request.topic,
            chat_room_id=request.chat_room_id,
        )

        return InterventionResponse(
            success=result.success,
            should_intervene=result.should_intervene,
            message=result.message,
            intervention_type=result.intervention_type.value if hasattr(result.intervention_type, 'value') else str(result.intervention_type),
            confidence=result.confidence,
            reason=result.reason,
            error=result.error,
        )

    except Exception as e:
        logger.error("intervention_analysis_failed", error=str(e))
        return InterventionResponse(
            success=False,
            should_intervene=False,
            message="",
            intervention_type="error",
            confidence=0,
            reason=str(e),
            error=str(e),
        )


@router.post(
    "/intervention/summary",
    response_model=SummaryResponse,
    tags=["Intervention"],
    summary="Generate discussion summary",
    description="Generate a summary of a group chat discussion with optional action items.",
)
async def generate_summary(request: SummaryRequest):
    """
    Generate a discussion summary from chat messages.
    Called by Core API's generateSummary method.
    """
    try:
        intervention_service = get_intervention_service()

        # Convert schema messages to dict format
        messages_dicts = [
            {
                "sender": msg.sender,
                "content": msg.content,
                "timestamp": msg.timestamp,
                "sender_id": msg.sender_id,
            }
            for msg in request.messages
        ]

        result = await intervention_service.generate_summary(
            messages=messages_dicts,
            chat_room_id=request.chat_room_id,
        )

        return SummaryResponse(
            success=result.success,
            summary=result.message,
            message_count=len(request.messages),
            error=result.error,
        )

    except Exception as e:
        logger.error("summary_generation_failed", error=str(e))
        return SummaryResponse(
            success=False,
            summary="",
            message_count=len(request.messages),
            error=str(e),
        )


@router.post(
    "/intervention/prompt",
    response_model=PromptResponse,
    tags=["Intervention"],
    summary="Generate discussion prompt",
    description="Generate a discussion prompt for a given topic to stimulate student engagement.",
)
async def generate_prompt(request: PromptRequest):
    """
    Generate a discussion prompt for a topic.
    Called by Core API's generatePrompt method.
    """
    try:
        intervention_service = get_intervention_service()

        result = await intervention_service.generate_discussion_prompt(
            topic=request.topic,
            context=request.context,
            difficulty=request.difficulty,
        )

        return PromptResponse(
            success=result.success,
            prompt=result.message,
            topic=request.topic,
            error=result.error,
        )

    except Exception as e:
        logger.error("prompt_generation_failed", error=str(e))
        return PromptResponse(
            success=False,
            prompt="",
            topic=request.topic,
            error=str(e),
        )


@router.get(
    "/analytics/group/{group_id}",
    response_model=GroupAnalyticsResponse,
    tags=["Analytics"],
    summary="Get group analytics (alias)",
    description="Alias for /analytics/dashboard/group/{group_id} - called by Core API.",
)
async def get_group_analytics_alias(group_id: str):
    """
    Get aggregated analytics for a group's discussion.
    This is an alias endpoint that Core API calls at /analytics/group/{group_id}.
    Delegates to the same logic as /analytics/dashboard/group/{group_id}.
    """
    try:
        orchestrator = get_orchestrator()
        data = await orchestrator.get_group_dashboard_data(group_id)

        return GroupAnalyticsResponse(
            success=True,
            group_id=group_id,
            message_count=data.get("message_count", 0),
            quality_score=data.get("quality_score"),
            quality_breakdown=data.get("quality_breakdown") or {},
            recommendation=data.get("recommendation"),
            participants=data.get("participants") or [],
            participant_count=data.get("participant_count", 0),
            engagement_distribution=data.get("engagement_distribution") or {},
            hot_percentage=data.get("hot_percentage"),
        )

    except Exception as e:
        logger.error("group_analytics_alias_failed", error=str(e), group_id=group_id)
        return GroupAnalyticsResponse(
            success=False,
            group_id=group_id,
            error=str(e),
        )


@router.get(
    "/analytics/export",
    tags=["Analytics"],
    summary="Export process mining data (general)",
)
async def export_process_mining_general(format: Optional[str] = Query(None, description="Response format: 'csv' for raw file, default is JSON metadata")):
    """
    General process mining export endpoint called by Core API.
    
    Default (no format param): Returns JSON with success, file_url, total_events, unique_cases.
    format=csv: Returns raw CSV file download.
    """
    try:
        mongo_logger = get_mongo_logger()
        csv_data = await mongo_logger.export_to_csv()

        lines = csv_data.strip().split('\n') if csv_data.strip() else []
        total_events = max(0, len(lines) - 1)
        
        unique_cases = 0
        if total_events > 0:
            case_ids = set()
            for line in lines[1:]:
                parts = line.split(',')
                if parts:
                    case_ids.add(parts[0])
            unique_cases = len(case_ids)

        if format == "csv":
            filename = f"process_mining_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            logger.info("process_mining_general_export_csv", size_bytes=len(csv_data))
            return Response(
                content=csv_data,
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )

        logger.info("process_mining_general_export_json", total_events=total_events, unique_cases=unique_cases)
        return JSONResponse(content={
            "success": True,
            "file_url": "/api/analytics/export?format=csv",
            "total_events": total_events,
            "unique_cases": unique_cases,
            "message": f"Export ready: {total_events} events across {unique_cases} cases",
        })

    except Exception as e:
        logger.error("process_mining_general_export_failed", error=str(e))
        return JSONResponse(content={
            "success": False,
            "file_url": "",
            "total_events": 0,
            "unique_cases": 0,
            "error": str(e),
        })


@router.delete(
    "/documents/{document_id}",
    tags=["Documents"],
    summary="Delete a document from the vector store",
)
async def delete_document(
    document_id: str,
    collection_name: Optional[str] = Query(None, description="Collection to delete from"),
):
    try:
        vector_store = get_vector_store()
        target_collection = collection_name or "default"

        await vector_store.delete_documents(
            where={"document_id": document_id},
            collection_name=target_collection,
        )

        logger.info("document_deleted", document_id=document_id, collection=target_collection)

        return JSONResponse(content={
            "success": True,
            "message": f"Document {document_id} deleted from {target_collection}",
        })

    except Exception as e:
        logger.error("document_delete_failed", error=str(e), document_id=document_id)
        raise HTTPException(status_code=500, detail=str(e))
