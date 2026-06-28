"""
Admin provider testing service.

Provides functionality to test AI provider connections by sending test prompts
and measuring latency. Used exclusively for admin provider configuration validation.
"""

import time
from typing import Any

from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

from app.core.logging import get_logger

logger = get_logger(__name__)


SUPPORTED_PROVIDERS = {"openai", "anthropic", "gemini"}

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
    "gemini": "gemini-2.0-flash-exp",
}


async def test_provider(
    name: str,
    api_key: str,
    base_url: str | None = None,
    model: str | None = None,
    test_prompt: str = "Hello",
) -> dict[str, Any]:
    """
    Test AI provider connection.

    Args:
        name: Provider name (openai, anthropic, gemini)
        api_key: Provider API key
        base_url: Optional custom base URL
        model: Model to test (uses default if not specified)
        test_prompt: Prompt to send for testing

    Returns:
        dict with keys: success, response?, latencyMs?, model?, error?

    Raises:
        ValueError: If provider is not supported
    """
    name = name.lower()

    if name not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported provider '{name}'. Supported: {', '.join(SUPPORTED_PROVIDERS)}"
        )

    # Use default model if not specified
    if not model:
        model = DEFAULT_MODELS.get(name)

    try:
        if name == "openai":
            return await _test_openai(api_key, base_url, model, test_prompt)
        elif name == "anthropic":
            return await _test_anthropic(api_key, model, test_prompt)
        elif name == "gemini":
            return await _test_gemini(api_key, model, test_prompt)
    except Exception as e:
        logger.error(f"Provider test failed for {name}: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }


async def _test_openai(
    api_key: str,
    base_url: str | None,
    model: str,
    test_prompt: str,
) -> dict[str, Any]:
    """Test OpenAI provider."""
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    start_time = time.time()

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": test_prompt}],
            max_tokens=50,
        )

        latency_ms = int((time.time() - start_time) * 1000)

        return {
            "success": True,
            "response": response.choices[0].message.content,
            "latencyMs": latency_ms,
            "model": response.model,
        }
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)

        # Provide helpful error messages
        if "401" in error_msg or "authentication" in error_msg.lower():
            error_msg = "Invalid API key - authentication failed"
        elif "404" in error_msg:
            error_msg = f"Model '{model}' not found or not accessible with this API key"
        elif "timeout" in error_msg.lower():
            error_msg = "Request timeout - provider API did not respond in time"

        return {
            "success": False,
            "error": error_msg,
            "latencyMs": latency_ms,
        }


async def _test_anthropic(
    api_key: str,
    model: str,
    test_prompt: str,
) -> dict[str, Any]:
    """Test Anthropic provider."""
    client = AsyncAnthropic(api_key=api_key)

    start_time = time.time()

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=50,
            messages=[{"role": "user", "content": test_prompt}],
        )

        latency_ms = int((time.time() - start_time) * 1000)

        # Extract text from response
        content = response.content[0].text if response.content else ""

        return {
            "success": True,
            "response": content,
            "latencyMs": latency_ms,
            "model": response.model,
        }
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)

        # Provide helpful error messages
        if "401" in error_msg or "authentication" in error_msg.lower():
            error_msg = "Invalid API key - authentication failed"
        elif "404" in error_msg or "not_found" in error_msg.lower():
            error_msg = f"Model '{model}' not found or not accessible with this API key"
        elif "timeout" in error_msg.lower():
            error_msg = "Request timeout - provider API did not respond in time"

        return {
            "success": False,
            "error": error_msg,
            "latencyMs": latency_ms,
        }


async def _test_gemini(
    api_key: str,
    model: str,
    test_prompt: str,
) -> dict[str, Any]:
    """Test Gemini provider."""
    # Note: Gemini implementation requires google-generativeai package
    # For now, return placeholder - full implementation TBD
    logger.warning("Gemini provider testing not yet fully implemented")

    return {
        "success": False,
        "error": "Gemini provider testing not yet implemented. Please test manually.",
    }
