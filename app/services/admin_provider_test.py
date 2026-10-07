"""
Admin provider testing service.

Provides functionality to test AI provider connections by sending test prompts
and measuring latency. Used exclusively for admin provider configuration validation.

This service uses the OpenAI-compatible API standard, which means it works with
any provider that implements the OpenAI API format (OpenAI, Anthropic, Gemini,
local models, etc.) by simply configuring the base_url and api_key.

Security note (SSRF fix H2): error responses returned to the caller never echo
the target's response body/HTML. Only a short, sanitized error class is sent;
the full exception (including any body) is kept in the server logs.
"""

import html
import re
import time
from typing import Any

from openai import AsyncOpenAI

from app.core.logging import get_logger

logger = get_logger(__name__)


DEFAULT_MODEL = "gpt-4o-mini"
MAX_ERROR_LEN = 200
_HTML_TAG_RE = re.compile(r"<[^>]{0,512}>")


def sanitize_error_text(raw: str) -> str:
    """Strip markup, collapse whitespace and cap the length.

    Keeps reflected error messages safe to return to the caller even when the
    underlying exception embedded a target response body.
    """
    text = _HTML_TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    text = " ".join(text.split())
    if not text:
        return "Unknown error"
    if len(text) > MAX_ERROR_LEN:
        text = text[: MAX_ERROR_LEN - 3].rstrip() + "..."
    return text


def classify_error(exc: Exception, model: str) -> str:
    """Map an exception to a short, safe error class.

    Never returns the target's response body/HTML: HTTP status errors are
    reported by status code only, everything else is reduced to the exception
    class plus a sanitized, truncated message.
    """
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        if status in (401, 403):
            raw = "Authentication failed - check the API key"
        elif status == 404:
            raw = f"Endpoint or model '{model}' not found (HTTP 404)"
        elif status == 429:
            raw = "Rate limited by provider (HTTP 429)"
        elif status >= 500:
            raw = f"Provider server error (HTTP {status})"
        elif status >= 400:
            raw = f"Provider rejected the request (HTTP {status})"
        else:
            raw = f"Provider returned HTTP {status}"
        return sanitize_error_text(raw)

    name = type(exc).__name__
    text = str(exc)
    lowered = text.lower()

    if "timeout" in name.lower() or "timeout" in lowered:
        raw = "Request timeout - provider API did not respond in time"
    elif "connection" in name.lower() or "connection" in lowered:
        raw = f"Connection error: {text}" if text else "Connection error"
    elif text:
        raw = f"{name}: {text}"
    else:
        raw = name

    return sanitize_error_text(raw)


async def test_provider(
    name: str,
    api_key: str,
    base_url: str | None = None,
    model: str | None = None,
    test_prompt: str = "Hello",
) -> dict[str, Any]:
    """
    Test AI provider connection using OpenAI-compatible API.

    Works with any provider that implements the OpenAI API format by configuring
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

    start_time = time.time()

    try:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

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
        # Safe, short error class for the caller...
        error_msg = classify_error(e, model)
        # ...full detail (class, message, traceback) stays server-side only.
        logger.error(
            f"Provider test failed for {name}: {type(e).__name__}: {e}",
            exc_info=True,
        )

        return {
            "success": False,
            "error": error_msg,
            "latencyMs": latency_ms,
        }
