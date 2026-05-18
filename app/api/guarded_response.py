from __future__ import annotations

from typing import Literal

from fastapi.responses import JSONResponse

from app.middleware.request_id import REQUEST_ID_HEADER

GuardedSurface = Literal["chat", "non_chat"]

RULE_MESSAGE_MAP: dict[str, str] = {
    "academic_dishonesty": "Saya tidak bisa langsung mengerjakan tugas. Mari saya bantu Anda memahami konsepnya.",
    "off_topic": "Pertanyaan ini di luar materi kuliah. Mari kembali ke topik diskusi.",
    "prompt_injection": "Permintaan tidak dapat diproses karena mengandung pola yang tidak diizinkan.",
    "toxicity": "Mari kita jaga diskusi tetap konstruktif.",
    "pii": "Mohon hindari membagikan data pribadi.",
}

DEFAULT_GUARDED_MESSAGE = "Maaf, permintaan ini tidak dapat diproses."


def guarded_response(
    rule_id: str,
    surface: GuardedSurface,
    request_id: str,
) -> JSONResponse:
    message = RULE_MESSAGE_MAP.get(rule_id, DEFAULT_GUARDED_MESSAGE)
    status_code = 200 if surface == "chat" else 403
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": "GUARDED",
            "outcome": "guarded",
            "reason": rule_id,
            "message": message,
            "request_id": request_id,
        },
        headers={REQUEST_ID_HEADER: request_id},
    )
