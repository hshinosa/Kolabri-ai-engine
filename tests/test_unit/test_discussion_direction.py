"""Unit tests for discussion direction routes (classify-relevance, session-summary)."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())

from app.api.routes import discussion_direction as dd
from app.services.llm import LLMResponse


def _llm(content: str | None, *, success: bool = True) -> LLMResponse:
    return LLMResponse(
        content=content or "",
        tokens_used=1,
        model="test",
        success=success,
        error=None if success else "fail",
    )


class TestParseJsonObject:
    def test_plain_json(self):
        assert dd._parse_json_object('{"a": 1}') == {"a": 1}

    def test_markdown_fence(self):
        raw = '```json\n{"classifications": []}\n```'
        assert dd._parse_json_object(raw) == {"classifications": []}

    def test_invalid_then_brace_extract(self):
        text = 'note {"goalAchieved": true, "topics": ["x"]} tail'
        parsed = dd._parse_json_object(text)
        assert parsed is not None
        assert parsed["goalAchieved"] is True

    def test_unrecoverable_returns_none(self):
        assert dd._parse_json_object("not json at all") is None

    def test_brace_match_invalid_json_returns_none(self):
        assert dd._parse_json_object("prefix {not valid json} suffix") is None


@pytest.mark.asyncio
async def test_classify_relevance_empty_goal_defaults_true():
    body = dd.ClassifyRelevanceRequest(
        messages=[dd.ClassifyMessageItem(id="m1", content="hi")],
        goal="   ",
    )
    out = await dd.classify_relevance(body)
    assert out.classifications == [{"messageId": "m1", "isRelevant": True}]


@pytest.mark.asyncio
async def test_classify_relevance_llm_success():
    body = dd.ClassifyRelevanceRequest(
        messages=[
            dd.ClassifyMessageItem(id="a", content="one"),
            dd.ClassifyMessageItem(id="b", content="two"),
        ],
        goal="Belajar SQL",
    )
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value=_llm(
            '{"classifications":[{"messageId":"a","isRelevant":false},{"messageId":"b","isRelevant":true}]}'
        )
    )
    with patch.object(dd, "get_llm_service", return_value=llm):
        out = await dd.classify_relevance(body)
    assert out.classifications == [
        {"messageId": "a", "isRelevant": False},
        {"messageId": "b", "isRelevant": True},
    ]


@pytest.mark.asyncio
async def test_classify_relevance_skips_items_without_message_id():
    body = dd.ClassifyRelevanceRequest(
        messages=[dd.ClassifyMessageItem(id="only", content="msg")],
        goal="Tujuan",
    )
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value=_llm(
            '{"classifications":[{"isRelevant":false},{"messageId":"only","isRelevant":true}]}'
        )
    )
    with patch.object(dd, "get_llm_service", return_value=llm):
        out = await dd.classify_relevance(body)
    assert out.classifications == [{"messageId": "only", "isRelevant": True}]


@pytest.mark.asyncio
async def test_classify_relevance_pads_missing_ids():
    body = dd.ClassifyRelevanceRequest(
        messages=[dd.ClassifyMessageItem(id="x", content="msg")],
        goal="Tujuan",
    )
    llm = MagicMock()
    llm.generate = AsyncMock(return_value=_llm('{"classifications":[]}'))
    with patch.object(dd, "get_llm_service", return_value=llm):
        out = await dd.classify_relevance(body)
    assert out.classifications == [{"messageId": "x", "isRelevant": True}]


@pytest.mark.asyncio
async def test_session_summary_llm_failure_uses_default():
    body = dd.SessionSummaryRequest(
        messages=[dd.SessionSummaryMessage(content="halo", senderName="A")],
        goal="G1",
    )
    llm = MagicMock()
    llm.generate = AsyncMock(return_value=_llm(None, success=False))
    with patch.object(dd, "get_llm_service", return_value=llm):
        out = await dd.session_summary(body)
    assert out.goalAchieved is False
    assert out.contributions == {"A": 1}
    assert "tidak tersedia" in out.assessment.lower()


@pytest.mark.asyncio
async def test_session_summary_parses_llm_json():
    body = dd.SessionSummaryRequest(
        messages=[
            dd.SessionSummaryMessage(content="diskusi", senderName=" Budi "),
        ],
        goal="",
        stats=dd.SessionSummaryStats(totalMessages=5, participantCount=2),
    )
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value=_llm(
            '{"goalAchieved": true, "topics": ["t1", "t2"], '
            '"contributions": {"Budi": 3}, "assessment": "Bagus sekali."}'
        )
    )
    with patch.object(dd, "get_llm_service", return_value=llm):
        out = await dd.session_summary(body)
    assert out.goalAchieved is True
    assert out.topics == ["t1", "t2"]
    assert out.contributions == {"Budi": 3}
    assert out.assessment == "Bagus sekali."


@pytest.mark.asyncio
async def test_session_summary_invalid_topics_and_assessment_fallback():
    body = dd.SessionSummaryRequest(
        messages=[dd.SessionSummaryMessage(content="x", senderName="")],
        goal="MyGoal",
    )
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value=_llm(
            '{"goalAchieved": false, "topics": "nope", "contributions": "bad", "assessment": "  "}'
        )
    )
    with patch.object(dd, "get_llm_service", return_value=llm):
        out = await dd.session_summary(body)
    assert out.topics == ["MyGoal"]
    assert out.contributions == {"Peserta": 1}
    assert "tidak tersedia" in out.assessment.lower()


@pytest.mark.asyncio
async def test_session_summary_unparseable_json_returns_default():
    body = dd.SessionSummaryRequest(
        messages=[dd.SessionSummaryMessage(content="x", senderName="Z")],
        goal="G",
    )
    llm = MagicMock()
    llm.generate = AsyncMock(return_value=_llm("totally not json"))
    with patch.object(dd, "get_llm_service", return_value=llm):
        out = await dd.session_summary(body)
    assert out.goalAchieved is False
    assert out.contributions == {"Z": 1}
