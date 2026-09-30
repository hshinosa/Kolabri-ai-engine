"""
Unit tests for the M2/M4 provider-response cache at generate()
(events: llm_provider_cache) and the M0 prompt-cache usage metrics
(event: llm_prompt_cache_usage).
"""

import asyncio
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import settings
from app.services.llm import OpenAILLMService


# ==============================================================================
# FIXTURES / HELPERS
# ==============================================================================


def _completion(content="Provider answer", usage=None):
    resp = MagicMock()
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    resp.choices = [choice]
    resp.usage = usage
    return resp


def _service(create: AsyncMock | None = None):
    """Build an OpenAILLMService wired to a mock client (test_llm.py pattern)."""
    mock_client = MagicMock()
    mock_client.chat.completions.create = create or AsyncMock(
        return_value=_completion()
    )
    with (
        patch("app.services.llm.httpx.AsyncClient"),
        patch("app.services.llm.settings") as mock_settings,
        patch("app.services.llm.AsyncOpenAI", return_value=mock_client),
    ):
        mock_settings.OPENAI_API_KEY = "test_key"
        mock_settings.OPENAI_BASE_URL = "https://api.test.com"
        mock_settings.OPENAI_MODEL = "test-model"
        mock_settings.OPENAI_TEMPERATURE = 0.7
        mock_settings.OPENAI_MAX_TOKENS = 1000
        mock_settings.UNIFIED_PROVIDER_ENABLED = False
        service = OpenAILLMService()
    return service, mock_client


def _cache_events(mock_logger):
    return [
        c
        for c in mock_logger.info.call_args_list
        if c.args and c.args[0] == "llm_provider_cache"
    ]


def _usage_events(mock_logger):
    return [
        c
        for c in mock_logger.info.call_args_list
        if c.args and c.args[0] == "llm_prompt_cache_usage"
    ]


# ==============================================================================
# M2/M4: provider-response cache
# ==============================================================================


@pytest.mark.asyncio
async def test_generate_miss_then_hit_reuses_provider_response():
    """Same inputs within a run: 1 provider call, second call served from cache."""
    service, client = _service()

    with patch("app.services.llm.logger") as mock_logger:
        first = await service.generate("hello")
        second = await service.generate("hello")

    assert client.chat.completions.create.await_count == 1
    assert first.content == "Provider answer"
    assert second.content == "Provider answer"

    events = _cache_events(mock_logger)
    assert [c.kwargs["result"] for c in events] == ["miss", "hit"]
    assert events[0].kwargs["success"] is True
    assert events[0].kwargs["model"] == "test-model"
    assert events[1].kwargs["model"] == "test-model"


@pytest.mark.asyncio
async def test_generate_cache_key_distinguishes_inputs_and_params():
    """Different prompt, temperature or max_tokens must not share a response."""
    service, client = _service()

    await service.generate("alpha")
    await service.generate("beta")
    await service.generate("alpha", temperature=0.1)
    await service.generate("alpha", temperature=0.9)
    await service.generate("alpha", max_tokens=42)

    assert client.chat.completions.create.await_count == 5


@pytest.mark.asyncio
async def test_failed_response_is_not_cached():
    """success=False responses always go back to the provider."""
    mock_client_response = _completion()
    service, client = _service(
        create=AsyncMock(side_effect=[RuntimeError("bad"), mock_client_response])
    )

    first = await service.generate("flaky")
    second = await service.generate("flaky")

    assert first.success is False
    assert second.success is True
    assert second.content == "Provider answer"
    assert client.chat.completions.create.await_count == 2


@pytest.mark.asyncio
async def test_exception_path_is_not_cached():
    """An exception raised out of generate() leaves the cache untouched."""
    service, client = _service()

    boom = Exception("provider down")
    with patch.object(
        service, "_execute_via_provider", AsyncMock(side_effect=boom)
    ):
        with pytest.raises(Exception) as exc_info:
            await service.generate("doomed")
        assert exc_info.value is boom

    # Real provider path again: must be a fresh call, not a cached failure.
    result = await service.generate("doomed")
    assert result.success is True
    assert client.chat.completions.create.await_count == 1


@pytest.mark.asyncio
async def test_concurrent_identical_requests_coalesce_to_one_call():
    """Single-flight: N identical concurrent generates = 1 provider call."""
    async def slow_create(**kwargs):
        await asyncio.sleep(0.05)
        return _completion("one shot")

    service, client = _service(create=AsyncMock(side_effect=slow_create))

    results = await asyncio.gather(
        *(service.generate("same prompt") for _ in range(5))
    )

    assert client.chat.completions.create.await_count == 1
    assert all(r.success for r in results)
    assert {r.content for r in results} == {"one shot"}


@pytest.mark.asyncio
async def test_efficiency_guard_disabled_bypasses_cache():
    """ENABLE_EFFICIENCY_GUARD=false -> every request reaches the provider."""
    service, client = _service()

    with patch.object(settings, "ENABLE_EFFICIENCY_GUARD", False):
        await service.generate("guarded")
        await service.generate("guarded")

    assert client.chat.completions.create.await_count == 2


# ==============================================================================
# M0: prompt-cache usage metrics
# ==============================================================================


@pytest.mark.asyncio
async def test_prompt_cache_usage_logged_on_non_stream_response():
    usage = SimpleNamespace(
        total_tokens=10, prompt_cache_hit_tokens=7, prompt_cache_miss_tokens=3
    )
    create = AsyncMock(return_value=_completion("ok", usage=usage))
    service, _ = _service(create=create)

    with patch("app.services.llm.logger") as mock_logger:
        await service.generate("usage please")

    events = _usage_events(mock_logger)
    assert len(events) == 1
    assert events[0].kwargs == {
        "hit": 7,
        "miss": 3,
        "model": "test-model",
    }


@pytest.mark.asyncio
async def test_prompt_cache_usage_absent_does_not_log():
    usage = SimpleNamespace(total_tokens=10)  # provider without cache counters
    create = AsyncMock(return_value=_completion("ok", usage=usage))
    service, _ = _service(create=create)

    with patch("app.services.llm.logger") as mock_logger:
        await service.generate("no usage attrs")
        await service.generate("no usage attrs")  # cache hit still no metric

    assert _usage_events(mock_logger) == []


def _stream_chunk(content=None, usage=None):
    chunk = MagicMock()
    if content is None:
        chunk.choices = []
    else:
        delta = MagicMock()
        delta.content = content
        chunk.choices = [MagicMock(delta=delta)]
    chunk.usage = usage
    return chunk


@pytest.mark.asyncio
async def test_prompt_cache_usage_logged_on_stream_final_chunk():
    usage = SimpleNamespace(
        total_tokens=9, prompt_cache_hit_tokens=4, prompt_cache_miss_tokens=5
    )
    chunks = [
        _stream_chunk("Hello"),
        _stream_chunk(" world"),
        _stream_chunk(None, usage=usage),
    ]

    async def agen():
        for c in chunks:
            yield c

    create = AsyncMock(return_value=agen())
    service, _ = _service(create=create)

    with patch("app.services.llm.logger") as mock_logger:
        tokens = []
        async for token in service.stream_generate("stream me"):
            tokens.append(token)

    assert tokens == ["Hello", " world"]
    events = _usage_events(mock_logger)
    assert len(events) == 1
    assert events[0].kwargs == {
        "hit": 4,
        "miss": 5,
        "model": "test-model",
    }
