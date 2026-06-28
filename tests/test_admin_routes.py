"""
Tests for admin provider routes.

Tests the /api/admin/test-provider and /api/admin/providers/{provider}/models endpoints.

Note: With the unified OpenAI-compatible approach, any provider name is accepted
as long as the base_url and api_key are valid. Provider validation is not enforced
at the API level since the system works with any OpenAI-compatible endpoint.
"""

import pytest
import httpx
from fastapi import status


TEST_HEADERS = {"Authorization": "Bearer test-token"}


@pytest.mark.asyncio
async def test_test_provider_openai_success(async_httpx_client: httpx.AsyncClient):
    """Test successful OpenAI provider test."""
    response = await async_httpx_client.post(
        "/api/admin/test-provider",
        json={
            "name": "openai",
            "apiKey": "test-key",
            "testPrompt": "Hello",
        },
        headers=TEST_HEADERS,
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, dict)
    assert "success" in data


@pytest.mark.asyncio
async def test_test_provider_any_compatible(async_httpx_client: httpx.AsyncClient):
    """Test that any provider name works (OpenAI-compatible approach)."""
    response = await async_httpx_client.post(
        "/api/admin/test-provider",
        json={
            "name": "custom-provider",
            "apiKey": "test-key",
            "baseUrl": "https://api.example.com/v1",
            "testPrompt": "Hello",
        },
        headers=TEST_HEADERS,
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, dict)
    assert "success" in data


@pytest.mark.asyncio
async def test_get_models_openai(async_httpx_client: httpx.AsyncClient):
    """Test fetching OpenAI models."""
    response = await async_httpx_client.get(
        "/api/admin/providers/openai/models",
        headers=TEST_HEADERS,
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "success" in data
    assert "models" in data
    assert isinstance(data["models"], list)


@pytest.mark.asyncio
async def test_get_models_anthropic(async_httpx_client: httpx.AsyncClient):
    """Test fetching Anthropic models (hardcoded list)."""
    response = await async_httpx_client.get(
        "/api/admin/providers/anthropic/models",
        headers=TEST_HEADERS,
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert len(data["models"]) > 0


@pytest.mark.asyncio
async def test_get_models_with_refresh(async_httpx_client: httpx.AsyncClient):
    """Test fetching models with cache refresh."""
    response = await async_httpx_client.get(
        "/api/admin/providers/openai/models?refresh=true",
        headers=TEST_HEADERS,
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "cached" in data


@pytest.mark.asyncio
async def test_get_models_invalid_provider(async_httpx_client: httpx.AsyncClient):
    """Test fetching models with invalid provider."""
    response = await async_httpx_client.get(
        "/api/admin/providers/invalid/models",
        headers=TEST_HEADERS,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
