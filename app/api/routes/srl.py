"""
SRL Zimmerman — endpoint klasifikasi ringan untuk pesan diskusi biasa.

Jalur `handle_message_stream` hanya berjalan untuk pesan @ai, sehingga pesan
biasa mahasiswa tidak pernah terklasifikasi. Endpoint ini dipanggil core-api
(fire-and-forget) untuk setiap pesan non-@ai: mengklasifikasi fase SRL
(forethought / performance / reflection) dan, **hanya bila ada sinyal nyata**
(indicators tidak kosong), menuliskan event `Student_Message` ke
`activity_logs` — koleksi yang sama dengan jalur @ai, dengan CaseID format
`<groupId>_session_<sessionDiscussionId>` sehingga analitik dosen
(gabungan per sesi/kelompok/kelas) ikut terisi.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.services.mongodb_logger import get_mongo_logger
from app.services.srl_classifier_enhanced import get_enhanced_srl_classifier

logger = get_logger(__name__)

router = APIRouter()


class SrlClassifyRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=20000)
    group_id: str
    chat_room_id: str
    user_id: str = "unknown"
    topic: Optional[str] = None


class SrlClassifyResponse(BaseModel):
    success: bool
    phase: str
    sub_phase: str
    confidence: float
    indicators: list
    logged: bool


@router.post("/srl/classify", response_model=SrlClassifyResponse, tags=["SRL"])
async def classify_srl(req: SrlClassifyRequest) -> SrlClassifyResponse:
    result = get_enhanced_srl_classifier().classify(req.message)

    logged = False
    if result.indicators:
        # Hanya pesan bersinyal yang dicatat — pesan tanpa sinyal (default)
        # tidak ditulis supaya distribusi fase mencerminkan sinyal nyata.
        try:
            await get_mongo_logger().log_activity(
                {
                    "CaseID": f"{req.group_id}_session_{req.chat_room_id}",
                    "Activity": "Student_Message",
                    "Timestamp": datetime.now(),
                    "Resource": f"Student_{req.user_id}",
                    "Lifecycle": "complete",
                    "Attributes": {
                        "original_text": req.message,
                        "srl_object": req.topic or "General",
                        "scaffolding_trigger": False,
                        "srl_phase": result.phase.value,
                        "srl_sub_phase": result.sub_phase,
                        "srl_confidence": round(float(result.confidence), 3),
                        "srl_indicators": ",".join(result.indicators[:10]),
                    },
                }
            )
            logged = True
        except Exception as exc:  # pragma: no cover - logging must never break chat
            logger.warning("srl_classify_log_failed", error=str(exc))

    return SrlClassifyResponse(
        success=True,
        phase=result.phase.value,
        sub_phase=result.sub_phase,
        confidence=round(float(result.confidence), 3),
        indicators=list(result.indicators),
        logged=logged,
    )
