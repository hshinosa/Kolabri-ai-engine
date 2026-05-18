from __future__ import annotations

from typing import Literal

from app.core.guardrails import GuardrailAction, GuardrailResult
from app.core.logging import get_logger

logger = get_logger(__name__)


def log_guardrail_decision(
    result: GuardrailResult,
    surface: Literal["input", "output"],
    route: str = "unknown",
) -> None:
    """Emit one structured `guardrail_decision` log line per material guardrail decision."""
    triggered = result.triggered_rules or []
    if result.action == GuardrailAction.ALLOW and not triggered:
        return
    rule_id = triggered[0] if triggered else result.reason or ""
    logger.info(
        "guardrail_decision",
        action=result.action.value,
        rule_id=rule_id,
        confidence=result.confidence,
        triggered_rules=list(triggered),
        surface=surface,
        route=route,
    )
