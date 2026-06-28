"""
Model discovery service.

Fetches available models from AI provider APIs with 1-hour caching.
Used by admin UI to populate model selection dropdown.
"""

import time
from typing import Any
from cachetools import TTLCache

from openai import AsyncOpenAI

from app.core.logging import get_logger

logger = get_logger(__name__)


SUPPORTED_PROVIDERS = {"openai", "anthropic", "gemini"}

# Cache: provider -> (models, timestamp)
# TTL: 1 hour (3600 seconds)
_model_cache: TTLCache = TTLCache(maxsize=10, ttl=3600)


# Anthropic models (hardcoded - no discovery API)
ANTHROPIC_MODELS = [
    {
        "id": "claude-3-5-sonnet-20241022",
        "name": "Claude 3.5 Sonnet",
        "description": "Most intelligent model - best for complex tasks",
        "contextWindow": 200000,
    },
    {
        "id": "claude-3-5-haiku-20241022",
        "name": "Claude 3.5 Haiku",
        "description": "Fastest model - best for simple tasks",
        "contextWindow": 200000,
    },
    {
        "id": "claude-3-opus-20240229",
        "name": "Claude 3 Opus",
        "description": "Previous generation flagship",
        "contextWindow": 200000,
    },
    {
        "id": "claude-3-sonnet-20240229",
        "name": "Claude 3 Sonnet",
        "description": "Previous generation balanced",
        "contextWindow": 200000,
    },
    {
        "id": "claude-3-haiku-20240307",
        "name": "Claude 3 Haiku",
        "description": "Previous generation fast",
        "contextWindow": 200000,
    },
]


async def fetch_models(
    provider: str,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    Fetch available models from provider API.

    Returns cached models (1-hour TTL) unless force_refresh=True.

    Args:
        provider: Provider name (openai, anthropic, gemini)
        force_refresh: Bypass cache and fetch fresh data

    Returns:
        dict with keys: success, models, cached, error?

    Raises:
        ValueError: If provider is not supported
    """
    provider = provider.lower()

    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported provider '{provider}'. Supported: {', '.join(SUPPORTED_PROVIDERS)}"
        )

    # Check cache first (unless force refresh)
    if not force_refresh and provider in _model_cache:
        logger.info(f"Returning cached models for {provider}")
        return {
            "success": True,
            "models": _model_cache[provider],
            "cached": True,
        }

    # Fetch fresh models
    try:
        if provider == "openai":
            models = await _fetch_openai_models()
        elif provider == "anthropic":
            models = _fetch_anthropic_models()
        elif provider == "gemini":
            models = await _fetch_gemini_models()
        else:
            models = []

        # Cache the result
        _model_cache[provider] = models

        logger.info(f"Fetched {len(models)} models for {provider}")

        return {
            "success": True,
            "models": models,
            "cached": False,
        }
    except Exception as e:
        logger.error(f"Model discovery failed for {provider}: {e}", exc_info=True)

        # Return cached data if available, even if expired
        if provider in _model_cache:
            logger.warning(f"Returning stale cache for {provider} due to error")
            return {
                "success": True,
                "models": _model_cache[provider],
                "cached": True,
            }

        return {
            "success": False,
            "models": [],
            "cached": False,
            "error": f"Failed to fetch models: {str(e)}",
        }


async def _fetch_openai_models() -> list[dict[str, Any]]:
    """
    Fetch models from OpenAI API.

    Uses OpenAI's list models endpoint.
    Note: Requires valid API key from environment or config.
    """
    # For model discovery, we can use a generic client
    # Admin will provide their own key for testing, but for discovery
    # we might need a system-level key or accept errors

    try:
        # Try to use env var or return common models as fallback
        import os

        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            logger.warning(
                "No OPENAI_API_KEY for model discovery, returning common models"
            )
            return _get_openai_common_models()

        client = AsyncOpenAI(api_key=api_key)
        response = await client.models.list()

        # Filter to only chat models (gpt-*)
        models = []
        for model in response.data:
            if model.id.startswith("gpt-"):
                models.append(
                    {
                        "id": model.id,
                        "name": model.id.upper().replace("-", " "),
                        "description": None,
                        "contextWindow": _get_openai_context_window(model.id),
                        "inputCost": None,  # OpenAI doesn't expose pricing via API
                        "outputCost": None,
                    }
                )

        # Sort by ID (newest first)
        models.sort(key=lambda m: m["id"], reverse=True)

        return models
    except Exception as e:
        logger.warning(f"OpenAI model API failed: {e}, returning common models")
        return _get_openai_common_models()


def _get_openai_common_models() -> list[dict[str, Any]]:
    """Return commonly used OpenAI models as fallback."""
    return [
        {
            "id": "gpt-4o",
            "name": "GPT-4o",
            "description": "Most advanced model",
            "contextWindow": 128000,
        },
        {
            "id": "gpt-4o-mini",
            "name": "GPT-4o Mini",
            "description": "Affordable and fast",
            "contextWindow": 128000,
        },
        {
            "id": "gpt-4-turbo",
            "name": "GPT-4 Turbo",
            "description": "Previous flagship",
            "contextWindow": 128000,
        },
        {
            "id": "gpt-4",
            "name": "GPT-4",
            "description": "Original GPT-4",
            "contextWindow": 8192,
        },
        {
            "id": "gpt-3.5-turbo",
            "name": "GPT-3.5 Turbo",
            "description": "Fast and affordable",
            "contextWindow": 16385,
        },
    ]


def _get_openai_context_window(model_id: str) -> int:
    """Get context window size for OpenAI model."""
    if "gpt-4o" in model_id or "gpt-4-turbo" in model_id:
        return 128000
    elif "gpt-4" in model_id:
        return 8192
    elif "gpt-3.5-turbo" in model_id:
        return 16385
    return 4096


def _fetch_anthropic_models() -> list[dict[str, Any]]:
    """
    Return Anthropic models (hardcoded).

    Anthropic doesn't have a model discovery API yet.
    """
    return ANTHROPIC_MODELS.copy()


async def _fetch_gemini_models() -> list[dict[str, Any]]:
    """
    Fetch models from Gemini API.

    Note: Requires google-generativeai package.
    For now, return common models as fallback.
    """
    logger.warning("Gemini model discovery not yet fully implemented")

    # Return common Gemini models
    return [
        {
            "id": "gemini-2.0-flash-exp",
            "name": "Gemini 2.0 Flash (Experimental)",
            "description": "Fastest and most advanced",
            "contextWindow": 1000000,
        },
        {
            "id": "gemini-1.5-pro",
            "name": "Gemini 1.5 Pro",
            "description": "Best for complex reasoning",
            "contextWindow": 2000000,
        },
        {
            "id": "gemini-1.5-flash",
            "name": "Gemini 1.5 Flash",
            "description": "Fast and versatile",
            "contextWindow": 1000000,
        },
    ]
