"""
Admin endpoints for provider testing and model discovery.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.services.admin_provider_test import test_provider
from app.services.model_discovery import fetch_models

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ============================================
# Schemas
# ============================================


class TestProviderRequest(BaseModel):
    """Request to test AI provider connection."""

    name: str = Field(..., description="Provider name: openai, anthropic, gemini")
    apiKey: str = Field(..., description="Provider API key")
    baseUrl: str | None = Field(None, description="Optional custom base URL")
    model: str | None = Field(
        None, description="Model to test (uses provider default if not specified)"
    )
    testPrompt: str = Field("Hello", description="Prompt to send for testing")


class TestProviderResponse(BaseModel):
    """Response from provider test."""

    success: bool
    response: str | None = None
    latencyMs: int | None = None
    model: str | None = None
    error: str | None = None


class ModelMetadata(BaseModel):
    """Model metadata from provider."""

    id: str
    name: str
    description: str | None = None
    contextWindow: int | None = None
    inputCost: float | None = None
    outputCost: float | None = None


class ModelListResponse(BaseModel):
    """Response with list of available models."""

    success: bool
    models: list[ModelMetadata]
    cached: bool
    error: str | None = None


# ============================================
# Endpoints
# ============================================


@router.post("/test-provider", response_model=TestProviderResponse)
async def test_provider_endpoint(request: TestProviderRequest) -> TestProviderResponse:
    """
    Test AI provider connection with provided credentials.

    Sends a test prompt to the provider and returns success/failure with latency.
    Used by admin UI to validate provider configuration before saving.
    """
    try:
        result = await test_provider(
            name=request.name,
            api_key=request.apiKey,
            base_url=request.baseUrl,
            model=request.model,
            test_prompt=request.testPrompt,
        )
        return TestProviderResponse(**result)
    except ValueError as e:
        # Validation errors (unsupported provider, invalid config)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Provider test error: {e}", exc_info=True)
        return TestProviderResponse(
            success=False,
            error=f"Provider test failed: {str(e)}",
        )


@router.get("/providers/{provider}/models", response_model=ModelListResponse)
async def get_provider_models(
    provider: str,
    refresh: bool = Query(False, description="Force cache refresh"),
) -> ModelListResponse:
    """
    Fetch available models from provider API.

    Returns cached models (1-hour TTL) unless refresh=true is passed.
    Used by admin UI to populate model dropdown for provider configuration.
    """
    try:
        result = await fetch_models(provider=provider, force_refresh=refresh)
        return ModelListResponse(**result)
    except ValueError as e:
        # Validation errors (unsupported provider)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Model discovery error for {provider}: {e}", exc_info=True)
        return ModelListResponse(
            success=False,
            models=[],
            cached=False,
            error=f"Unable to fetch models from provider. Please manually enter model ID. Error: {str(e)}",
        )
