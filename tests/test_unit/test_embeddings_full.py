from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import embeddings
from app.services.embeddings import GeminiEmbeddingService, get_embedding_service


def _response(payload):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    return response


@pytest.fixture
def mock_http_client():
    client = MagicMock()
    client.post = AsyncMock()
    return client


@pytest.fixture
def service(mock_http_client):
    with patch("app.services.embeddings.httpx.AsyncClient", return_value=mock_http_client):
        with patch.object(embeddings.settings, "GEMINI_API_KEY", "gemini-test-key"), patch.object(
            embeddings.settings, "GOOGLE_API_KEY", ""
        ), patch.object(
            embeddings.settings,
            "GEMINI_EMBEDDING_MODEL",
            "models/text-embedding-004",
        ):
            instance = GeminiEmbeddingService()
            instance.initialize()
            yield instance


@pytest.mark.unit
@pytest.mark.asyncio
async def test_embed_text_full(service, mock_http_client):
    mock_http_client.post.return_value = _response({"embedding": {"values": [0.1, 0.2]}})

    res = await service.embed_text("test")

    assert res == [0.1, 0.2]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_embed_texts_full(service, mock_http_client):
    mock_http_client.post.return_value = _response(
        {"embeddings": [{"values": [0.1]}, {"values": [0.2]}]}
    )

    res = await service.embed_texts(["t1", "t2"])
    assert res == [[0.1], [0.2]]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_embed_query_full(service, mock_http_client):
    mock_http_client.post.return_value = _response({"embedding": {"values": [0.4, 0.5]}})

    res = await service.embed_query("query")

    assert res == [0.4, 0.5]


@pytest.mark.unit
def test_initialize_twice(mock_http_client):
    with patch("app.services.embeddings.httpx.AsyncClient", return_value=mock_http_client):
        with patch.object(embeddings.settings, "GEMINI_API_KEY", "gemini-test-key"), patch.object(
            embeddings.settings, "GOOGLE_API_KEY", ""
        ), patch.object(
            embeddings.settings,
            "GEMINI_EMBEDDING_MODEL",
            "models/text-embedding-004",
        ):
            instance = GeminiEmbeddingService()
            instance.initialize()
            first_client = instance._client
            instance.initialize()

    assert instance._client is first_client


@pytest.mark.unit
def test_singleton():
    embeddings._embedding_service = None

    s1 = get_embedding_service()
    s2 = get_embedding_service()

    assert s1 is s2
