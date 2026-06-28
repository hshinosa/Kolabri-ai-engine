"""
Admin provider testing service.

Provides functionality to test AI provider connections by sending test prompts
and measuring latency. Used exclusively for admin provider configuration validation.

This service uses the OpenAI-compatible API standard, which means it works with
any provider that implements the OpenAI API format (OpenAI, Anthropic, Gemini,
local models, etc.) by simply configuring the base_url and api_key.
"""

import time
from typing import Any

from openai import AsyncOpenAI

from app.core.logging import get_logger

logger = get_logger(__name__)


DEFAULT_MODEL = "gpt-4o-mini"


async def test_provider(
    name: str,
    api_key: str,
    base_url: str | None = None,
    model: str | None = None,
    test_prompt: str = "Hello",
) -> dict[str, Any]:
    """
    Test AI provider connection using OpenAI-compatible API.

    Works with any provider that implements OpenAI API format by configuring
    the base_url appropriately:
    - OpenAI: base_url = None (uses default)
    - Anthropic: base_url = provider's OpenAI-compatible endpoint
    - Gemini: base_url = provider's OpenAI-compatible endpoint
    - Any other: base_url = custom endpoint

    Args:
        name: Provider name (for logging/display only)
        api_key: Provider API key
        base_url: Optional custom base URL for OpenAI-compatible endpoint
        model: Model to test (uses default if not specified)
        test_prompt: Prompt to send for testing

    Returns:
        dict with keys: success, response?, latencyMs?, model?, error?
    """
    if not model:
        model = DEFAULT_MODEL

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

        if "401" in error_msg or "authentication" in error_msg.lower():
            error_msg = "Invalid API key - authentication failed"
        elif "404" in error_msg:
            error_msg = f"Model '{model}' not found or not accessible with this API key"
        elif "timeout" in error_msg.lower():
            error_msg = "Request timeout - provider API did not respond in time"

        logger.error(f"Provider test failed for {name}: {error_msg}", exc_info=True)

        return {
            "success": False,
            "error": error_msg,
            "latencyMs": latency_ms,
        }
