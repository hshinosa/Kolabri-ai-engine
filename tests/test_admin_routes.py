"""
Tests for admin provider routes.

Tests the /api/admin/test-provider and /api/admin/providers/{provider}/models endpoints.
"""

import pytest
from httpx import AsyncClient
from fastapi import status


@pytest.mark.asyncio
async def test_test_provider_openai_success(client: AsyncClient):
    """Test successful OpenAI provider test."""
    response = await client.post(
        "/api/admin/test-provider",
        json={
            "name": "openai",
            "apiKey": "test-key",
            "testPrompt": "Hello",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, dict)
    assert "success" in data


@pytest.mark.asyncio
async def test_test_provider_invalid_provider(client: AsyncClient):
    """Test provider test with invalid provider name."""
    response = await client.post(
        "/api/admin/test-provider",
        json={
            "name": "invalid-provider",
            "apiKey": "test-key",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_get_models_openai(client: AsyncClient):
    """Test fetching OpenAI models."""
    response = await client.get("/api/admin/providers/openai/models")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "success" in data
    assert "models" in data
    assert isinstance(data["models"], list)


@pytest.mark.asyncio
async def test_get_models_anthropic(client: AsyncClient):
    """Test fetching Anthropic models (hardcoded list)."""
    response = await client.get("/api/admin/providers/anthropic/models")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert len(data["models"]) > 0


@pytest.mark.asyncio
async def test_get_models_with_refresh(client: AsyncClient):
    """Test fetching models with cache refresh."""
    response = await client.get("/api/admin/providers/openai/models?refresh=true")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "cached" in data


@pytest.mark.asyncio
async def test_get_models_invalid_provider(client: AsyncClient):
    """Test fetching models with invalid provider."""
    response = await client.get("/api/admin/providers/invalid/models")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
