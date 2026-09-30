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
        raise HTTPException(status_code=400, detail=str(e)) from e
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
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Model discovery error for {provider}: {e}", exc_info=True)
        return ModelListResponse(
            success=False,
            models=[],
            cached=False,
            error=f"Unable to fetch models from provider. Please manually enter model ID. Error: {str(e)}",
        )


class ModelDiscoveryRequest(BaseModel):
    """Model discovery with explicit OpenAI-compatible credentials."""

    provider: str = Field(..., description="Provider name")
    refresh: bool = Field(False, description="Force cache refresh")
    baseUrl: str | None = Field(None, description="OpenAI-compatible base URL")
    apiKey: str | None = Field(None, description="API key for the listing request")


@router.post("/providers/{provider}/models", response_model=ModelListResponse)
async def post_provider_models(
    provider: str, request: ModelDiscoveryRequest
) -> ModelListResponse:
    """
    Fetch available models using explicit credentials (kept in the POST body
    so keys never appear in request URLs or logs).
    """
    try:
        result = await fetch_models(
            provider=provider,
            force_refresh=request.refresh,
            base_url=request.baseUrl,
            api_key=request.apiKey,
        )
        return ModelListResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Model discovery error for {provider}: {e}", exc_info=True)
        return ModelListResponse(
            success=False,
            models=[],
            cached=False,
            error=f"Unable to fetch models from provider. Please manually enter model ID. Error: {str(e)}",
        )


# ============================================
# Embedding Configuration
# ============================================


class EmbeddingConfigResponse(BaseModel):
    """Current embedding configuration."""

    provider: str
    voyageModel: str | None = None
    voyageOutputDimension: int | None = None
    voyageConfigured: bool
    localModel: str | None = None
    activeProvider: str
    degraded: bool = False


class EmbeddingConfigUpdate(BaseModel):
    """Switch embedding provider at runtime."""

    provider: str = Field(..., description="Target provider: 'voyage' or 'local'")


@router.get("/embedding-config", response_model=EmbeddingConfigResponse)
async def get_embedding_config() -> EmbeddingConfigResponse:
    """Report the active embedding provider and its configuration."""
    from app.core.config import settings
    from app.services.embeddings import get_embedding_service

    svc = get_embedding_service()
    provider_name = "local" if getattr(svc, "degraded", False) else settings.EMBEDDING_PROVIDER
    return EmbeddingConfigResponse(
        provider=provider_name,
        voyageModel=settings.VOYAGE_MODEL if not getattr(svc, "degraded", False) else None,
        voyageOutputDimension=settings.VOYAGE_OUTPUT_DIMENSION if not getattr(svc, "degraded", False) else None,
        voyageConfigured=bool(settings.VOYAGE_API_KEY),
        localModel=settings.EMBEDDING_MODEL,
        activeProvider=type(svc).__name__,
        degraded=bool(getattr(svc, "degraded", False)),
    )


@router.put("/embedding-config")
async def update_embedding_config(request: EmbeddingConfigUpdate) -> dict:
    """Switch embedding provider at runtime (voyage <-> local)."""
    from app.core.config import settings
    from app.services import embeddings as embeddings_module

    provider = request.provider.strip().lower()
    if provider not in ("voyage", "local"):
        raise HTTPException(status_code=422, detail="provider must be 'voyage' or 'local'")
    if provider == "voyage" and not settings.VOYAGE_API_KEY:
        raise HTTPException(status_code=409, detail="VOYAGE_API_KEY is not configured")

    embeddings_module._embedding_service = None
    settings.EMBEDDING_PROVIDER = provider
    svc = embeddings_module.get_embedding_service()
    logger.info(
        "embedding_provider_switched",
        provider=provider,
        service=type(svc).__name__,
    )
    return {
        "data": {
            "provider": provider,
            "activeService": type(svc).__name__,
            # Avoid touching svc.dimension: for the local provider that would
            # eagerly download/load the ONNX model and stall the request.
            "dimension": settings.VOYAGE_OUTPUT_DIMENSION if provider == "voyage" else None,
        }
    }
