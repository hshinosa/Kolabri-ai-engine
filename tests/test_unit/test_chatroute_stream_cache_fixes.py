"""personal_chat_stream: prefix-reordered prompt + chunk-replay cache.

Covers the three changes in app/api/routes/chat.py:
- non-stream POST /chat/personal removed (stream stays),
- RAG context moved from the system prompt into the leading user turn,
- SHA-256 keyed chunk-replay cache with single-flight dedup (errors uncached).
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("redis.asyncio", MagicMock())
sys.modules.setdefault("redis", MagicMock())
sys.modules.setdefault("prometheus_client", MagicMock())

from app.api.routes import chat as chat_routes
from app.api.schemas import PersonalChatRequest


def _chat_client() -> TestClient:
    app = FastAPI()
    app.include_router(chat_routes.router)
    return TestClient(app)


async def _stream(chunks: list[str]):
    for content in chunks:
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
        )


def _mock_llm(stream_chunks: list[str]) -> MagicMock:
    mock_llm = MagicMock()
    mock_llm.ensure_ready = AsyncMock()
    mock_llm.model = "gpt-test"
    mock_llm.client.chat.completions.create = AsyncMock(
        return_value=_stream(stream_chunks)
    )
    return mock_llm


@pytest.mark.asyncio
async def test_stream_replays_cached_chunks_without_second_provider_call():
    """Two identical requests served by the same loop: one provider stream,
    byte-identical replayed SSE events, miss logged first then hit."""
    mock_llm = _mock_llm(["Halo ", "dunia"])
    request = PersonalChatRequest(message="probe-cache-replay", history=[])

    with patch(
        "app.api.routes.chat.get_llm_service", return_value=mock_llm
    ), patch.object(chat_routes, "logger") as mock_logger:
        first = await chat_routes.personal_chat_stream(request)
        first_events = [event async for event in first.body_iterator]
        second = await chat_routes.personal_chat_stream(request)
        second_events = [event async for event in second.body_iterator]

    assert first_events[0] == 'data: {"content": "Halo "}\n\n'
    assert first_events == second_events
    assert first_events[-1] == "data: [DONE]\n\n"
    assert mock_llm.client.chat.completions.create.await_count == 1

    cache_logs = [
        call.kwargs
        for call in mock_logger.info.call_args_list
        if call.args and call.args[0] == "llm_prompt_cache"
    ]
    assert [entry["result"] for entry in cache_logs] == ["miss", "hit"]


@pytest.mark.asyncio
async def test_stream_error_response_is_not_cached():
    """A failed stream must not poison the cache: every retry re-tries the
    provider and yields the same error event."""
    mock_llm = _mock_llm([])
    mock_llm.client.chat.completions.create = AsyncMock(side_effect=Exception("boom"))
    request = PersonalChatRequest(message="probe-error-not-cached", history=[])

    with patch("app.api.routes.chat.get_llm_service", return_value=mock_llm):
        first = await chat_routes.personal_chat_stream(request)
        first_events = [event async for event in first.body_iterator]
        second = await chat_routes.personal_chat_stream(request)
        second_events = [event async for event in second.body_iterator]

    assert first_events == second_events
    assert 'data: {"error": "Internal error"}\n\n' in first_events
    assert "data: [DONE]\n\n" not in first_events
    assert mock_llm.client.chat.completions.create.await_count == 2


def test_stream_missing_route_for_non_stream_chat():
    """POST /chat/personal (non-stream) was removed; only the stream route
    remains."""
    client = _chat_client()
    response = client.post("/chat/personal", json={"message": "Halo", "history": []})

    assert response.status_code == 404


def test_rag_context_moved_to_user_turn_system_prompt_stays_byte_identical():
    """M1: system prompt must be exactly PERSONAL_CHAT_SYSTEM_PROMPT on every
    request; the dynamic RAG block + citation instruction lead the user turn,
    history turns untouched, all instruction texts still present."""
    rag_results = [
        {
            "content": "Materi dasar Python dibahas minggu 3",
            "metadata": {"source": "Modul Python", "page": 3},
            "score": 0.9,
            "_course_id": "if101",
        }
    ]
    expected_context, expected_citations = chat_routes.build_rag_context_and_citations(
        rag_results
    )
    expected_block = chat_routes.RAG_CONTEXT_PROMPT.format(
        context=expected_context
    ) + chat_routes.CITATION_INSTRUCTION
    message = "probe-prefix-order materi Python di minggu keberapa?"
    history = [
        {"role": "user", "content": "Halo"},
        {"role": "assistant", "content": "Hai juga"},
    ]

    mock_llm = _mock_llm(["Minggu 3"])
    with patch(
        "app.api.routes.chat.get_llm_service", return_value=mock_llm
    ), patch(
        "app.api.routes.chat.search_personal_rag",
        new=AsyncMock(return_value=rag_results),
    ):
        response = _chat_client().post(
            "/chat/personal/stream",
            json={"message": message, "course_ids": ["if101"], "history": history},
        )

    assert response.status_code == 200
    assert expected_citations  # fixture sanity: citations were produced

    messages = mock_llm.client.chat.completions.create.await_args.kwargs["messages"]
    # System prompt byte-identical to the static base — no dynamic context.
    assert messages[0] == {
        "role": "system",
        "content": chat_routes.PERSONAL_CHAT_SYSTEM_PROMPT,
    }
    # Prior turns unchanged.
    assert messages[1] == {"role": "user", "content": "Halo"}
    assert messages[2] == {"role": "assistant", "content": "Hai juga"}
    # Dynamic context + citation instruction now lead the user turn.
    assert messages[-1] == {
        "role": "user",
        "content": f"{expected_block}\n\n{message}",
    }
    user_content = messages[-1]["content"]
    assert "Berikut adalah materi kuliah yang relevan" in user_content
    assert "Ketika merujuk materi" in user_content
    assert user_content.endswith(message)
    # Citations still reach the client as an SSE event.
    assert '"citations"' in response.text
    assert "Modul Python" in response.text


@pytest.mark.asyncio
async def test_concurrent_identical_streams_share_one_provider_call():
    """Single-flight: while the leader is still streaming, an identical
    concurrent request waits instead of fanning out, then replays the same
    events."""
    gate = asyncio.Event()
    create_started = asyncio.Event()

    async def _gated_create(**kwargs):
        create_started.set()
        await gate.wait()
        return _stream(["tertunda", " bersama"])

    mock_llm = _mock_llm([])
    mock_llm.client.chat.completions.create = AsyncMock(side_effect=_gated_create)
    request = PersonalChatRequest(message="probe-single-flight", history=[])

    with patch("app.api.routes.chat.get_llm_service", return_value=mock_llm):
        leader_response = await chat_routes.personal_chat_stream(request)
        waiter_response = await chat_routes.personal_chat_stream(request)

        async def _collect(generator):
            return [event async for event in generator]

        leader_task = asyncio.create_task(_collect(leader_response.body_iterator))
        await create_started.wait()

        waiter_task = asyncio.create_task(_collect(waiter_response.body_iterator))
        await asyncio.sleep(0.05)
        # Leader is still blocked inside the provider call and nothing is
        # cached yet — the waiter must be parked on the in-flight leader.
        assert not waiter_task.done()

        gate.set()
        leader_events, waiter_events = await asyncio.gather(leader_task, waiter_task)

    assert mock_llm.client.chat.completions.create.await_count == 1
    assert leader_events == waiter_events
    assert leader_events[-1] == "data: [DONE]\n\n"


def test_build_stream_cache_key_tracks_every_input():
    """The cache key must change when any response-affecting input changes."""
    base = {
        "model": "model-a",
        "system_prompt": "system-a",
        "history": [SimpleNamespace(role="user", content="hi")],
        "user_content": "user-a",
    }
    key = chat_routes.build_stream_cache_key(**base)
    assert key == chat_routes.build_stream_cache_key(**base)
    assert len(key) == 64

    for field, other in (
        ("model", "model-b"),
        ("system_prompt", "system-b"),
        ("user_content", "user-b"),
    ):
        changed = dict(base)
        changed[field] = other
        assert chat_routes.build_stream_cache_key(**changed) != key

    changed_history = dict(base)
    changed_history["history"] = [SimpleNamespace(role="user", content="bye")]
    assert chat_routes.build_stream_cache_key(**changed_history) != key
