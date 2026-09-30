"""
Regression tests for the prefix-cache fixes in the RAG pipeline.

M1b — _synthesize_answer: the system prompt must stay byte-identical across
requests (static base instructions only); the retrieval context + instruction
blocks lead the user message; chat history rides as ordered messages; the
dynamic scaffolding context moves out of the system prompt.

M2c — query_stream NO_FETCH: identical requests replay the recorded chunks
from a TTL cache with a single provider call; failed streams are never
cached; distinct prompts never share a cache entry.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.guardrails import GuardrailAction
from app.core.prompt_templates import (
    RAG_FEW_SHOT,
    SYSTEM_PERSONAL_CHAT,
    SYSTEM_RAG,
    TEMPERATURE,
)
from app.services import rag as rag_module
from app.services.circuit_breaker import get_llm_circuit_breaker
from app.services.llm import ChatMessage, OpenAILLMService
from app.services.rag import RAGPipeline


STATIC_RAG_SYSTEM = SYSTEM_RAG + "\n\n" + RAG_FEW_SHOT


@pytest.fixture(autouse=True)
def _isolate_runtime_state():
    """Module-level chunk cache and breaker singleton must not leak across tests."""
    breaker = get_llm_circuit_breaker()
    breaker.reset()
    rag_module._stream_chunk_cache.clear()
    yield
    rag_module._stream_chunk_cache.clear()
    breaker.reset()


@pytest.fixture
def llm_recorder():
    """Real OpenAILLMService wired to a mock client that records sent messages."""
    with (
        patch("app.services.llm.httpx.AsyncClient"),
        patch("app.services.llm.settings") as mock_settings,
        patch("app.services.llm.AsyncOpenAI") as mock_openai,
    ):
        mock_settings.OPENAI_API_KEY = "test_key"
        mock_settings.OPENAI_BASE_URL = "https://api.test.com"
        mock_settings.OPENAI_MODEL = "test-model"
        mock_settings.OPENAI_TEMPERATURE = 0.7
        mock_settings.OPENAI_MAX_TOKENS = 1000
        mock_settings.UNIFIED_PROVIDER_ENABLED = False

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Jawaban model"
        mock_response.usage.total_tokens = 10

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_openai.return_value = mock_client

        yield OpenAILLMService(), mock_client


@contextmanager
def _pipeline(llm_service):
    with (
        patch("app.services.rag.get_vector_store"),
        patch("app.services.rag.get_llm_service", return_value=llm_service),
        patch("app.services.rag.get_guardrails"),
        patch("app.services.rag.get_reranker"),
        patch("app.services.rag.RetrievalQualityControls.from_settings"),
        patch("app.services.rag.get_efficiency_guard"),
        patch("app.services.rag.settings") as mock_settings,
    ):
        mock_settings.ENABLE_EFFICIENCY_GUARD = False
        pipeline = RAGPipeline(llm_service=llm_service)
        yield pipeline


def _allow_input(query, _guardrail_context=None):
    return MagicMock(
        action=GuardrailAction.ALLOW,
        sanitized_input=query,
        triggered_rules=[],
        reason=None,
    )


def _sent_messages(mock_client):
    return mock_client.chat.completions.create.call_args.kwargs["messages"]


def _recording_stream(chunks, fail_first=False):
    """Return (call recorder, stream_generate-compatible async gen)."""
    calls = []

    async def stream(**kwargs):
        calls.append(kwargs)
        if fail_first and len(calls) == 1:
            raise RuntimeError("provider down")
        for chunk in chunks:
            yield chunk

    return calls, stream


async def _collect(pipeline, query):
    return [event async for event in pipeline.query_stream(query=query)]


# ==============================================================================
# M1b: prefix reorder in _synthesize_answer
# ==============================================================================


@pytest.mark.asyncio
async def test_synthesize_answer_static_system_context_leads_user_message(
    llm_recorder,
):
    service, mock_client = llm_recorder

    with _pipeline(service) as pipeline:
        await pipeline._synthesize_answer(
            query="Apa itu gradient descent?",
            contexts=[
                {
                    "content": "Isi materi unik-XYZ tentang optimasi.",
                    "metadata": {"source": "ML.pdf", "page": 3},
                }
            ],
            chat_history=None,
            fading_level=0.0,
            guardrail_context=None,
        )
        first = _sent_messages(mock_client)

        await pipeline._synthesize_answer(
            query="Bagaimana cara kerja backpropagation?",
            contexts=[
                {
                    "content": "Konteks berbeda-ABC tentang neural network.",
                    "metadata": {"source": "DL.pdf", "page": 7},
                }
            ],
            chat_history=None,
            fading_level=0.0,
            guardrail_context=None,
        )
        second = _sent_messages(mock_client)

    # system = static base instructions only, byte-identical across requests
    assert first[0]["role"] == "system"
    assert first[0]["content"] == STATIC_RAG_SYSTEM
    assert second[0]["content"] == STATIC_RAG_SYSTEM
    assert "Isi materi unik-XYZ tentang optimasi." not in first[0]["content"]
    assert "Konteks berbeda-ABC tentang neural network." not in second[0]["content"]

    # retrieval context leads the user message, the query follows it
    first_user = first[-1]
    assert first_user["role"] == "user"
    assert first_user["content"].startswith("Konteks Dokumen:")
    assert "Isi materi unik-XYZ tentang optimasi." in first_user["content"]
    context_part, _, _ = first_user["content"].partition("Apa itu gradient descent?")
    assert "Isi materi unik-XYZ tentang optimasi." in context_part
    assert "Pertanyaan Mahasiswa: Apa itu gradient descent?" in first_user["content"]
    assert first_user["content"].rstrip().endswith("Jawaban:")
    assert "Konteks berbeda-ABC tentang neural network." in second[-1]["content"]

    # generation params unchanged by the reorder
    assert (
        mock_client.chat.completions.create.call_args.kwargs["temperature"]
        == TEMPERATURE["rag"]
    )


@pytest.mark.asyncio
async def test_synthesize_answer_history_rides_as_ordered_messages(llm_recorder):
    service, mock_client = llm_recorder

    with _pipeline(service) as pipeline:
        await pipeline._synthesize_answer(
            query="Lanjutannya seperti apa?",
            contexts=[
                {
                    "content": "Materi sesi lanjutan unik-HIST.",
                    "metadata": {"source": "Modul.pdf", "page": 2},
                }
            ],
            chat_history=[
                ChatMessage(role="user", content="Halo pertanyaan pertama"),
                ChatMessage(role="assistant", content="Ini jawaban pertama"),
            ],
            fading_level=0.0,
            guardrail_context=None,
        )
        messages = _sent_messages(mock_client)

    # history stays ordered between the static system prompt and the user turn
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[0]["content"] == STATIC_RAG_SYSTEM
    assert messages[1]["content"] == "Halo pertanyaan pertama"
    assert messages[2]["content"] == "Ini jawaban pertama"

    user_msg = messages[3]["content"]
    # context leads the user turn; the history block is not duplicated into it
    assert user_msg.startswith("Konteks Dokumen:")
    assert "Materi sesi lanjutan unik-HIST." in user_msg
    assert "Riwayat Diskusi" not in user_msg
    assert "Pertanyaan Terbaru: Lanjutannya seperti apa?" in user_msg
    assert user_msg.rstrip().endswith("Jawaban:")


@pytest.mark.asyncio
async def test_synthesize_answer_scaffolding_moved_out_of_system(llm_recorder):
    service, mock_client = llm_recorder

    with _pipeline(service) as pipeline:
        await pipeline._synthesize_answer(
            query="Jelaskan konsep ini",
            contexts=[
                {
                    "content": "Konteks scaffolding unik-SCAF.",
                    "metadata": {"source": "Bab.pdf", "page": 1},
                }
            ],
            chat_history=None,
            fading_level=0.0,
            guardrail_context={
                "scaffolding_config": {"enabled": True, "scaffolding_level": "early"}
            },
        )
        messages = _sent_messages(mock_client)

    # scaffolding is dynamic: it must not pollute the byte-identical system prompt
    assert messages[0]["content"] == STATIC_RAG_SYSTEM
    user_msg = messages[-1]["content"]
    assert "Scaffolding level for this cohort: early." in user_msg
    assert "Konteks scaffolding unik-SCAF." in user_msg


# ==============================================================================
# M2c: NO_FETCH chunk-replay cache in query_stream
# ==============================================================================


@pytest.mark.asyncio
async def test_query_stream_nofetch_identical_request_replays_single_provider_call():
    calls, stream = _recording_stream(["Halo", "!", " Ada yang bisa saya bantu?"])
    mock_llm = MagicMock()
    mock_llm.stream_generate = stream

    with _pipeline(mock_llm) as pipeline:
        pipeline.guardrails.check_input.side_effect = _allow_input

        query = "halo zq-replay-abc"
        first = await _collect(pipeline, query)
        second = await _collect(pipeline, query)

    # one provider round-trip; the second identical request replays verbatim
    assert len(calls) == 1
    assert first == second
    assert [e["type"] for e in first] == ["token", "token", "token", "done"]
    tokens = [e for e in first if e["type"] == "token"]
    assert "".join(e["content"] for e in tokens) == "Halo! Ada yang bisa saya bantu?"
    assert {"type": "done", "sources": [], "citations": []} in first
    # verified: NO_FETCH streams with the static personal-chat system prompt
    assert calls[0]["system_prompt"] == SYSTEM_PERSONAL_CHAT


@pytest.mark.asyncio
async def test_query_stream_nofetch_error_is_not_cached():
    calls, stream = _recording_stream(["Halo lagi"], fail_first=True)
    mock_llm = MagicMock()
    mock_llm.stream_generate = stream

    with _pipeline(mock_llm) as pipeline:
        pipeline.guardrails.check_input.side_effect = _allow_input

        query = "halo zq-error-abc"
        failed = await _collect(pipeline, query)
        retried = await _collect(pipeline, query)
        replayed = await _collect(pipeline, query)

    assert [e["type"] for e in failed] == ["error"]
    # the failed attempt never entered the cache: the retry still hits the provider
    assert len(calls) == 2
    assert [e["type"] for e in retried] == ["token", "done"]
    # the successful stream is now cacheable and replays identically
    assert len(calls) == 2
    assert replayed == retried


@pytest.mark.asyncio
async def test_query_stream_nofetch_distinct_prompts_do_not_share_cache_entry():
    calls, stream = _recording_stream(["Halo"])
    mock_llm = MagicMock()
    mock_llm.stream_generate = stream

    with _pipeline(mock_llm) as pipeline:
        pipeline.guardrails.check_input.side_effect = _allow_input

        await _collect(pipeline, "halo zq-distinct-a")
        await _collect(pipeline, "halo zq-distinct-b")

    assert len(calls) == 2
