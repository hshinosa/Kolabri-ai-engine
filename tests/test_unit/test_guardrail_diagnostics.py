from __future__ import annotations

import structlog

from app.core.guardrail_diagnostics import log_guardrail_decision
from app.core.guardrails import GuardrailAction, GuardrailResult


def _make_result(
    action: GuardrailAction,
    triggered: list[str] | None = None,
    confidence: float = 0.9,
    reason: str = "",
) -> GuardrailResult:
    return GuardrailResult(
        action=action,
        reason=reason,
        message=None,
        sanitized_input=None,
        confidence=confidence,
        triggered_rules=triggered,
    )


def test_block_emits_log(caplog):
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="abc-123")
    try:
        with structlog.testing.capture_logs() as captured:
            log_guardrail_decision(
                _make_result(
                    GuardrailAction.BLOCK,
                    triggered=["academic_dishonesty"],
                    confidence=0.95,
                    reason="academic_dishonesty",
                ),
                surface="input",
                route="/api/chat",
            )
    finally:
        structlog.contextvars.clear_contextvars()

    matching = [e for e in captured if e.get("event") == "guardrail_decision"]
    assert len(matching) == 1
    entry = matching[0]
    assert entry["action"] == "block"
    assert entry["rule_id"] == "academic_dishonesty"
    assert entry["confidence"] == 0.95
    assert entry["triggered_rules"] == ["academic_dishonesty"]
    assert entry["surface"] == "input"
    assert entry["route"] == "/api/chat"


def test_sanitize_emits_log():
    with structlog.testing.capture_logs() as captured:
        log_guardrail_decision(
            _make_result(
                GuardrailAction.SANITIZE,
                triggered=["pii"],
                confidence=0.7,
            ),
            surface="input",
            route="/api/chat",
        )
    matching = [e for e in captured if e.get("event") == "guardrail_decision"]
    assert len(matching) == 1
    assert matching[0]["action"] == "sanitize"
    assert matching[0]["rule_id"] == "pii"


def test_allow_with_no_rules_skips_log():
    with structlog.testing.capture_logs() as captured:
        log_guardrail_decision(
            _make_result(GuardrailAction.ALLOW, triggered=[]),
            surface="input",
            route="/api/chat",
        )
    matching = [e for e in captured if e.get("event") == "guardrail_decision"]
    assert matching == []


def test_allow_with_triggered_rules_still_emits():
    with structlog.testing.capture_logs() as captured:
        log_guardrail_decision(
            _make_result(
                GuardrailAction.ALLOW,
                triggered=["off_topic"],
                confidence=0.4,
            ),
            surface="output",
            route="/api/ask",
        )
    matching = [e for e in captured if e.get("event") == "guardrail_decision"]
    assert len(matching) == 1
    assert matching[0]["action"] == "allow"
    assert matching[0]["rule_id"] == "off_topic"
