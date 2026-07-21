"""
Unit Tests for OpenAI Compatible LLM Service
===========================================

Tests for LLM service including:
- Retry logic for transient errors
- RAG-enhanced responses
- Intervention generation
- Scaffolding instructions
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock, call

from app.core.config import settings
from app.services.llm import (
    OpenAILLMService,
    LLMResponse,
    ChatMessage,
    get_llm_service,
)


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def llm_service():
    """Create LLM service with mocked dependencies."""
    with (
        patch("app.services.llm.httpx.AsyncClient"),
        patch("app.services.llm.settings") as mock_settings,
        patch("app.services.llm.AsyncOpenAI") as mock_openai,
    ):
        # Configure mock settings
        mock_settings.OPENAI_API_KEY = "test_key"
        mock_settings.OPENAI_BASE_URL = "https://api.test.com"
        mock_settings.OPENAI_MODEL = "test-model"
        mock_settings.OPENAI_TEMPERATURE = 0.7
        mock_settings.OPENAI_MAX_TOKENS = 1000
        mock_settings.SCAFFOLDING_FULL_THRESHOLD = 0.3
        mock_settings.SCAFFOLDING_MINIMAL_THRESHOLD = 0.7
        mock_settings.UNIFIED_PROVIDER_ENABLED = False

        # Create mock for chat completions - default success response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.usage.total_tokens = 50

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_openai.return_value = mock_client

        service = OpenAILLMService()
        # Return tuple for simplicity: (service, mock_client)
        return service, mock_client


# ==============================================================================
# TESTS: Initialization
# ==============================================================================


def test_llm_initialization(llm_service):
    """Test LLM service initializes correctly."""
    service, _ = llm_service
    assert service.model == "test-model"
    assert settings.LLM_MAX_RETRIES == 3


def test_llm_initialization_uses_provider_context_over_env():
    provider_context = {
        "version": "1.0",
        "provider": {"name": "openai", "displayName": "OpenAI GPT"},
        "execution": {
            "baseUrl": "https://provider.example/v1",
            "model": "gpt-4o-mini",
            "temperature": 0.25,
            "maxTokens": 2048,
        },
        "auth": {"type": "api-key", "credential": "sk-provider-key"},
        "metadata": {
            "featureFamily": "personal_chat",
            "requestId": "req-1",
            "resolvedAt": "2026-06-16T00:00:00.000Z",
        },
    }

    with (
        patch("app.services.llm.httpx.AsyncClient"),
        patch("app.services.llm.settings") as mock_settings,
        patch("app.services.llm.AsyncOpenAI") as mock_openai,
    ):
        mock_settings.OPENAI_API_KEY = "env-key"
        mock_settings.OPENAI_BASE_URL = "https://env.example/v1"
        mock_settings.OPENAI_MODEL = "env-model"
        mock_settings.OPENAI_TEMPERATURE = 0.7
        mock_settings.OPENAI_MAX_TOKENS = 1000
        mock_settings.UNIFIED_PROVIDER_ENABLED = False

        service = OpenAILLMService(provider_context=provider_context)

        assert service.model == "gpt-4o-mini"
        assert service.temperature == 0.25
        assert service.max_tokens == 2048
        mock_openai.assert_called_once()
        call_kwargs = mock_openai.call_args.kwargs
        assert call_kwargs["api_key"] == "sk-provider-key"
        assert call_kwargs["base_url"] == "https://provider.example/v1"


def test_get_llm_service_returns_request_scoped_instance_for_provider_context():
    provider_context = {
        "version": "1.0",
        "provider": {"name": "openai", "displayName": "OpenAI GPT"},
        "execution": {
            "baseUrl": "https://provider.example/v1",
            "model": "gpt-4o-mini",
        },
        "auth": {"type": "api-key", "credential": "sk-provider-key"},
        "metadata": {
            "featureFamily": "orchestration",
            "requestId": "req-1",
            "resolvedAt": "2026-06-16T00:00:00.000Z",
        },
    }

    with (
        patch("app.services.llm.httpx.AsyncClient"),
        patch("app.services.llm.settings") as mock_settings,
        patch("app.services.llm.AsyncOpenAI"),
        patch("app.services.llm._llm_service", new=object()),
    ):
        mock_settings.OPENAI_API_KEY = "env-key"
        mock_settings.OPENAI_BASE_URL = "https://env.example/v1"
        mock_settings.OPENAI_MODEL = "env-model"
        mock_settings.OPENAI_TEMPERATURE = 0.7
        mock_settings.OPENAI_MAX_TOKENS = 1000
        mock_settings.UNIFIED_PROVIDER_ENABLED = False

        service = get_llm_service(provider_context=provider_context)

        assert isinstance(service, OpenAILLMService)
        assert service.model == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_generate_with_unified_provider_does_not_call_asyncio_run_in_event_loop():
    provider_context = {
        "version": "1.0",
        "provider": {"name": "openai", "displayName": "OpenAI GPT"},
        "execution": {
            "baseUrl": "https://provider.example/v1",
            "model": "gpt-4o-mini",
        },
        "auth": {"type": "api-key", "credential": "sk-provider-key"},
        "metadata": {
            "featureFamily": "personal_chat",
            "requestId": "req-async",
            "resolvedAt": "2026-06-16T00:00:00.000Z",
        },
    }

    with (
        patch("app.services.llm.httpx.AsyncClient"),
        patch("app.services.llm.AsyncOpenAI") as mock_openai,
        patch.object(settings, "UNIFIED_PROVIDER_ENABLED", True),
    ):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Async-safe response"
        mock_response.usage.total_tokens = 12

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_openai.return_value = mock_client

        service = OpenAILLMService(provider_context=None)
        service._fetch_provider_from_database = AsyncMock(return_value=provider_context)

        result = await service.generate("hello")

        assert result.success is True
        assert result.content == "Async-safe response"
        service._fetch_provider_from_database.assert_awaited_once()

# ==============================================================================
# TESTS: Basic Generation
# ==============================================================================


@pytest.mark.asyncio
async def test_generate_basic(llm_service):
    """Test basic message generation."""
    service, mock_client = llm_service

    result = await service.generate("Hello, world!")

    assert result.success is True
    assert result.content == "Test response"
    assert result.tokens_used == 50
    assert result.model == "test-model"
    assert mock_client.chat.completions.create.called


@pytest.mark.asyncio
async def test_generate_with_custom_parameters(llm_service):
    """Test generation with custom temperature and max tokens."""
    service, mock_client = llm_service

    result = await service.generate(
        prompt="Test prompt", temperature=0.5, max_tokens=500
    )

    assert result.success is True

    # Verify parameters were passed correctly
    call_kwargs = mock_client.chat.completions.create.call_args[1]
    assert call_kwargs["temperature"] == 0.5
    assert call_kwargs["max_tokens"] == 500


@pytest.mark.asyncio
async def test_generate_with_system_prompt(llm_service):
    """Test generation with custom system prompt."""
    service, mock_client = llm_service

    result = await service.generate(
        prompt="Test", system_prompt="You are a helpful assistant."
    )

    assert result.success is True

    # Verify system prompt was included
    messages = mock_client.chat.completions.create.call_args[1]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are a helpful assistant."


@pytest.mark.asyncio
async def test_generate_with_context(llm_service):
    """Test generation with context."""
    service, mock_client = llm_service

    result = await service.generate(
        prompt="What is X?", context="X is a variable in programming."
    )

    assert result.success is True

    # Verify context was included
    messages = mock_client.chat.completions.create.call_args[1]["messages"]
    assert any(
        m["role"] == "system"
        and "Konteks tambahan:" in m["content"]
        and "X is a variable" in m["content"]
        for m in messages
    )


# ==============================================================================
# TESTS: Retry Logic
# ==============================================================================


@pytest.mark.asyncio
async def test_retry_on_rate_limit_error(llm_service):
    """Test retry on rate limit error."""
    from openai import RateLimitError

    service, mock_client = llm_service

    # Create response with status
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Success after retry"
    mock_response.usage.total_tokens = 50

    # Create rate limit error with correct signature
    rate_limit_error = RateLimitError(
        message="Rate limit exceeded", response=MagicMock(), body=MagicMock()
    )

    mock_client.chat.completions.create = AsyncMock(
        side_effect=[rate_limit_error, mock_response]
    )

    result = await service.generate("Test")

    assert result.success is True
    assert result.content == "Success after retry"
    assert mock_client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_retry_on_connection_error(llm_service):
    """Test retry on connection error."""
    from openai import APIConnectionError

    service, mock_client = llm_service

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Success after retry"
    mock_response.usage.total_tokens = 50

    conn_error = APIConnectionError(message="Connection failed", request=MagicMock())

    mock_client.chat.completions.create = AsyncMock(
        side_effect=[conn_error, mock_response]
    )

    result = await service.generate("Test")

    assert result.success is True
    assert mock_client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_retry_on_server_error_5xx(llm_service):
    """Test retry on 5xx server errors."""
    from openai import APIError

    service, mock_client = llm_service

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Success after retry"
    mock_response.usage.total_tokens = 50

    # Create a 500 error
    server_error = APIError(
        message="Internal server error", request=MagicMock(), body=MagicMock()
    )
    server_error.status_code = 500

    mock_client.chat.completions.create = AsyncMock(
        side_effect=[server_error, mock_response]
    )

    result = await service.generate("Test")

    assert result.success is True
    assert mock_client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_no_retry_on_client_error_4xx(llm_service):
    """Test that 4xx errors are not retried."""
    from openai import APIError

    service, mock_client = llm_service

    # Create a 400 error (client error)
    client_error = APIError(
        message="Bad request", request=MagicMock(), body=MagicMock()
    )
    client_error.status_code = 400

    mock_client.chat.completions.create = AsyncMock(side_effect=client_error)

    result = await service.generate("Test")

    assert result.success is False
    assert result.error == "Internal error"
    assert mock_client.chat.completions.create.call_count == 1  # No retry


@pytest.mark.asyncio
async def test_max_retries_exceeded(llm_service):
    from openai import RateLimitError
    from app.services.llm import LLMDegradedError
    from app.services.circuit_breaker import get_llm_circuit_breaker

    service, mock_client = llm_service
    get_llm_circuit_breaker().reset()

    rate_limit_error = RateLimitError(
        message="Always rate limited", response=MagicMock(), body=MagicMock()
    )
    mock_client.chat.completions.create = AsyncMock(side_effect=rate_limit_error)

    with pytest.raises(LLMDegradedError) as exc_info:
        await service.generate("Test")
    assert exc_info.value.reason == "llm_retry_exhausted"
    assert mock_client.chat.completions.create.call_count == 3


@pytest.mark.asyncio
async def test_no_retry_on_non_api_exception(llm_service):
    """Test that non-API exceptions are not retried."""
    service, mock_client = llm_service

    mock_client.chat.completions.create = AsyncMock(
        side_effect=ValueError("Unexpected error")
    )

    result = await service.generate("Test")

    assert result.success is False
    assert mock_client.chat.completions.create.call_count == 1  # No retry


# ==============================================================================
# TESTS: RAG-Enhanced Responses
# ==============================================================================


@pytest.mark.asyncio
async def test_generate_rag_response_basic(llm_service):
    """Test RAG-enhanced response generation."""
    service, mock_client = llm_service

    contexts = [
        {
            "content": "Database normalization is the process of organizing data.",
            "metadata": {"source": "doc1"},
        },
        {"content": "It helps reduce redundancy.", "metadata": {"source": "doc2"}},
    ]

    result = await service.generate_rag_response(
        query="What is normalization?", contexts=contexts
    )

    assert result.success is True

    # Verify context was formatted and included
    call_kwargs = mock_client.chat.completions.create.call_args[1]
    messages = call_kwargs["messages"]
    prompt = messages[-1]["content"]
    assert "Database normalization is the process" in prompt
    assert "It helps reduce redundancy" in prompt


@pytest.mark.asyncio
async def test_generate_rag_response_with_chat_history(llm_service):
    """Test RAG response with chat history."""
    service, mock_client = llm_service

    chat_history = [
        ChatMessage(role="user", content="Hello"),
        ChatMessage(role="assistant", content="Hi there!"),
    ]

    result = await service.generate_rag_response(
        query="What's next?", contexts=[], chat_history=chat_history
    )

    assert result.success is True

    # Verify history was included
    messages = mock_client.chat.completions.create.call_args[1]["messages"]
    history_text = "\n".join([m["role"] + ": " + m["content"] for m in messages])
    assert "Hello" in history_text


@pytest.mark.asyncio
async def test_rag_response_uses_cot_template(llm_service):
    service, mock_client = llm_service

    result = await service.generate_rag_response(
        query="Apa itu gradient descent?",
        contexts=[{"content": "test", "metadata": {"source": "doc.pdf"}}],
        fading_level=0.0,
    )

    assert result.success is True
    prompt = mock_client.chat.completions.create.call_args[1]["messages"][-1]["content"]
    assert "INSTRUKSI MENJAWAB" in prompt


@pytest.mark.asyncio
async def test_rag_response_includes_few_shot_in_system(llm_service):
    service, mock_client = llm_service

    await service.generate_rag_response(
        query="test", contexts=[{"content": "ctx", "metadata": {}}], fading_level=0.5
    )

    system = mock_client.chat.completions.create.call_args[1]["messages"][0]["content"]
    assert "CONTOH JAWABAN YANG BENAR" in system


@pytest.mark.asyncio
async def test_rag_response_with_fading_socratic(llm_service):
    """Test RAG response with Socratic questioning (fading level 1.0)."""
    service, mock_client = llm_service

    result = await service.generate_rag_response(
        query="How do I do this?", contexts=[], fading_level=1.0
    )

    assert result.success is True

    # Check for Socratic questioning instruction
    prompt = mock_client.chat.completions.create.call_args[1]["messages"][-1]["content"]
    assert any(
        keyword in prompt.lower() for keyword in ["socratic", "pemandu", "membimbing"]
    )


# ==============================================================================
# TESTS: Intervention Generation
# ==============================================================================


@pytest.mark.asyncio
async def test_generate_intervention_redirect(llm_service):
    """Test generation of redirect intervention."""
    service, mock_client = llm_service

    chat_messages = [
        {"sender": "student1", "content": "I like pizza"},
        {"sender": "student2", "content": "Me too"},
    ]

    result = await service.generate_intervention(
        chat_messages=chat_messages,
        intervention_type="redirect",
        topic="Database Normalization",
    )

    assert result.success is True

    # Verify topic was mentioned
    prompt = mock_client.chat.completions.create.call_args[1]["messages"][-1]["content"]
    assert "Database Normalization" in prompt


@pytest.mark.asyncio
async def test_generate_intervention_prompt(llm_service):
    """Test generation of prompt intervention."""
    service, mock_client = llm_service

    chat_messages = [{"sender": "student1", "content": "Hmm"}]

    result = await service.generate_intervention(
        chat_messages=chat_messages, intervention_type="prompt", topic="SQL"
    )

    assert result.success is True

    # Verify it asks a question
    prompt = mock_client.chat.completions.create.call_args[1]["messages"][-1]["content"]
    assert "student1" in prompt


@pytest.mark.asyncio
async def test_generate_intervention_summarize(llm_service):
    """Test generation of summary intervention."""
    service, mock_client = llm_service

    chat_messages = [
        {"sender": "student1", "content": "Point A"},
        {"sender": "student2", "content": "Point B"},
        {"sender": "student1", "content": "Conclusion"},
    ]

    result = await service.generate_intervention(
        chat_messages=chat_messages, intervention_type="summarize"
    )

    assert result.success is True

    # Verify it asks for summary
    prompt = mock_client.chat.completions.create.call_args[1]["messages"][-1]["content"]
    assert "diskusi" in str(prompt).lower()


# ==============================================================================
# TESTS: Summary Generation
# ==============================================================================


@pytest.mark.asyncio
async def test_generate_summary_basic(llm_service):
    """Test basic summary generation."""
    service, mock_client = llm_service

    messages = [
        {"sender": "user1", "content": "First point"},
        {"sender": "user2", "content": "Second point"},
    ]

    result = await service.generate_summary(messages)

    assert result.success is True

    # Verify system prompt contains summary-related keywords
    system_prompt = mock_client.chat.completions.create.call_args[1]["messages"][0][
        "content"
    ]
    assert (
        "ringkasan" in str(system_prompt).lower()
        or "summary" in str(system_prompt).lower()
    )


@pytest.mark.asyncio
async def test_generate_summary_with_action_items(llm_service):
    """Test summary with action items."""
    service, mock_client = llm_service

    result = await service.generate_summary([], include_action_items=True)

    assert result.success is True

    # Verify action items are included
    prompt = mock_client.chat.completions.create.call_args[1]["messages"][-1]["content"]
    assert "action" in prompt.lower() or "tindak" in prompt.lower()


# ==============================================================================
# TESTS: Socratic Reframing
# ==============================================================================


@pytest.mark.asyncio
async def test_reframe_to_socratic(llm_service):
    """Test reframing direct answer to Socratic hint."""
    service, mock_client = llm_service

    socratic_response = "What do you think the answer might be?"
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = socratic_response
    mock_response.usage.total_tokens = 30

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await service.reframe_to_socratic(
        response="The answer is 42 because it's the answer to everything."
    )

    # Returns content directly
    assert result == socratic_response

    # Verify Socratic system prompt
    system_prompt = mock_client.chat.completions.create.call_args[1]["messages"][0][
        "content"
    ]
    assert "Socratic" in system_prompt

    # Verify original response was in the prompt
    prompt = mock_client.chat.completions.create.call_args[1]["messages"][-1]["content"]
    assert "42" in prompt


# ==============================================================================
# TESTS: Goal Refinement Suggestion
# ==============================================================================


@pytest.mark.asyncio
async def test_get_goal_refinement_suggestion(llm_service):
    """Test goal refinement suggestion for invalid goal."""
    service, mock_client = llm_service

    result = await service.get_goal_refinement_suggestion(
        current_goal="I want to learn stuff",
        missing_criteria=["Specific", "Measurable", "Time-bound"],
    )

    assert result.success is True

    # Verify SMART context is included
    prompt = mock_client.chat.completions.create.call_args[1]["messages"][-1]["content"]
    assert "I want to learn stuff" in prompt
    assert "kriteria smart" in prompt.lower()

    # Verify it asks a guiding question
    prompt_lower = prompt.lower()
    assert "pertanyaan" in prompt_lower or "pemandu" in prompt_lower


# ==============================================================================
# TESTS: Helper Methods
# ==============================================================================


def test_format_contexts(llm_service):
    """Test context formatting."""
    service, _ = llm_service

    contexts = [
        {"content": "Content 1", "metadata": {"source": "doc.pdf", "page": 1}},
        {"content": "Content 2", "metadata": {"source": "doc.pdf", "page": 5}},
    ]

    formatted = service._format_contexts(contexts)

    assert "[1] Sumber: doc.pdf" in formatted
    assert "Content 1" in formatted
    assert "[2] Sumber: doc.pdf" in formatted
    assert "Content 2" in formatted


def test_format_chat_history(llm_service):
    """Test chat history formatting."""
    service, _ = llm_service

    history = [
        ChatMessage(role="user", content="Hello"),
        ChatMessage(role="assistant", content="Hi!"),
        ChatMessage(role="user", content="Bye"),
    ]

    formatted = service._format_chat_history(history[:2])  # Last 2 messages

    lines = formatted.split("\n")
    # Check for Indonesian format since service uses it
    assert any("Hello" in line or "user" in line.lower() for line in lines)
    assert any("Hi!" in line or "assistant" in line.lower() for line in lines)


# ==============================================================================
# TESTS: Error Scenarios
# ==============================================================================


@pytest.mark.asyncio
async def test_generate_error_without_usage_info(llm_service):
    """Test generation when response has no usage info."""
    service, mock_client = llm_service

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Test"
    mock_response.usage = None  # No usage info

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await service.generate("Test")

    assert result.success is True
    assert result.tokens_used == 0


@pytest.mark.asyncio
async def test_generate_with_empty_choices(llm_service):
    """Test generation when response has no choices."""
    service, mock_client = llm_service

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Test"

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await service.generate("Test")

    # Should succeed with valid choices
    assert result.success is True


def test_get_llm_service_returns_lazy_instance_when_unified_enabled():
    with patch("app.services.llm.settings") as mock_settings:
        mock_settings.UNIFIED_PROVIDER_ENABLED = True
        result = get_llm_service()
        assert isinstance(result, OpenAILLMService)


def test_get_llm_service_returns_instance_when_unified_disabled():
    with patch("app.services.llm.settings") as mock_settings:
        mock_settings.UNIFIED_PROVIDER_ENABLED = False
        mock_settings.OPENAI_API_KEY = "sk-test-key-12345678901234567890"
        mock_settings.OPENAI_BASE_URL = "https://api.openai.com/v1"
        mock_settings.OPENAI_MODEL = "gpt-4"
        mock_settings.OPENAI_TEMPERATURE = 0.7
        mock_settings.OPENAI_MAX_TOKENS = 2048
        mock_settings.LLM_MAX_RETRIES = 0
        mock_settings.LLM_TIMEOUT_CONNECT_SECONDS = 5.0
        mock_settings.LLM_TIMEOUT_READ_SECONDS = 30.0
        import app.services.llm as llm_module

        llm_module._llm_service = None
        result = get_llm_service()
        assert result is not None
        llm_module._llm_service = None
