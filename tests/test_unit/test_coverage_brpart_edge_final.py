"""Force the last partial branch edges (chunking + goal_validator fence)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.document_processing.chunking import create_chunks
from app.services.goal_validator import strip_markdown_json_fence


def test_strip_fence_plain_json_unchanged():
    raw = '{"refined_goal": "x"}'
    assert strip_markdown_json_fence(raw) == raw


def test_strip_fence_removes_open_and_close():
    inner = '{"refined_goal": "y"}'
    assert strip_markdown_json_fence(f"```json\n{inner}\n```") == inner


def test_strip_fence_open_only_no_closing_line():
    inner = '{"refined_goal": "z"}'
    assert strip_markdown_json_fence(f"```json\n{inner}") == inner


def test_strip_fence_first_line_not_backticks_keeps_body():
    """Opening line does not start with ``` — inner pop skipped."""
    body = '{"refined_goal": "w"}'
    wrapped = f"```\n{body}\n```"
    assert strip_markdown_json_fence(wrapped) == body


def test_strip_fence_only_triple_backticks_returns_empty():
    assert strip_markdown_json_fence("```") == ""



def test_create_chunks_whitespace_only_window_skips_append():
    """69->87 false: slice is only spaces after strip."""
    text = "a" + " " * 12 + "b"
    chunks = create_chunks(text, "doc", "pad.txt", 1, 1, 0)
    assert [c.text for c in chunks] == ["a", "b"]


def test_create_chunks_exits_while_via_start_ge_len_not_condition():
    """57->95: loop ends with break when start >= len after advancing."""
    text = "M" * 61
    chunks = create_chunks(text, "doc", "f.txt", 1, 30, 0)
    assert len(chunks) == 3
    assert sum(len(c.text) for c in chunks) == 61


@pytest.mark.asyncio
async def test_goal_refine_open_fence_no_trailing_backtick_line():
    """382 true, 384 false: strip opener only (no closing ``` line)."""
    from app.services.goal_validator import GoalValidator

    validator = GoalValidator()
    payload = json.dumps({"refined_goal": "8 modul selesai", "explanation": "ok"})
    content = "```json\n" + payload
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        return_value=MagicMock(tokens_used=1, content=content)
    )
    with patch("app.services.llm.get_llm_service", return_value=mock_llm):
        result = await validator.refine_goal("Belajar rutin", ["measurable"])
    assert result["success"] is True


@pytest.mark.asyncio
async def test_goal_refine_strips_closing_fence_line():
    """384 true: last line is ``` and is removed."""
    from app.services.goal_validator import GoalValidator

    validator = GoalValidator()
    payload = json.dumps(
        {"refined_goal": "Menyelesaikan 6 latihan dalam 10 hari", "explanation": "ok"}
    )
    content = "```json\n" + payload + "\n```"
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        return_value=MagicMock(tokens_used=2, content=content)
    )
    with patch("app.services.llm.get_llm_service", return_value=mock_llm):
        result = await validator.refine_goal(
            "Belajar algoritma dengan jadwal mingguan", ["time_bound"]
        )
    assert result["success"] is True
    assert "latihan" in result["refined_goal"]