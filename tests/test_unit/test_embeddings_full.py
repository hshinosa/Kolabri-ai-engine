from unittest.mock import MagicMock, patch

import pytest

from app.services import embeddings
from app.services.embeddings import LocalEmbeddingService, get_embedding_service


def _mock_vector(values):
    vector = MagicMock()
    vector.tolist.return_value = list(values)
    vector.__len__.return_value = len(values)
    return vector


@pytest.fixture
def service():
    instance = LocalEmbeddingService()
    mock_model = MagicMock()
    mock_model.embed.return_value = iter([_mock_vector([0.11, 0.22])])
    mock_model.query_embed.return_value = iter([_mock_vector([0.33, 0.44])])
    instance._model = mock_model
    instance._initialized = True
    return instance


@pytest.mark.unit
@pytest.mark.asyncio
async def test_embed_text_full(service):
    res = await service.embed_text("test")

    assert res == [0.11, 0.22]
    service._model.embed.assert_called_once_with(["test"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_embed_texts_full(service):
    service._model.embed.return_value = iter([_mock_vector([0.1]), _mock_vector([0.2])])

    res = await service.embed_texts(["t1", "t2"])
    assert res == [[0.1], [0.2]]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_embed_query_full(service):
    res = await service.embed_query("query")

    assert res == [0.33, 0.44]
    service._model.query_embed.assert_called_once_with("query")


@pytest.mark.unit
def test_initialize_twice():
    mock_model = MagicMock()

    with patch("app.services.embeddings.TextEmbedding", return_value=mock_model) as mock_text_embedding:
        instance = LocalEmbeddingService()
        instance.initialize()
        first_model = instance._model
        instance.initialize()

    assert instance._model is first_model
    mock_text_embedding.assert_called_once_with(model_name=embeddings.settings.EMBEDDING_MODEL)


@pytest.mark.unit
def test_dimension_returns_embedding_length(service):
    service._model.embed.return_value = iter([_mock_vector([0.1, 0.2, 0.3, 0.4])])

    assert service.dimension == 4
    service._model.embed.assert_called_once_with(["test"])


@pytest.mark.unit
def test_singleton():
    embeddings._embedding_service = None

    s1 = get_embedding_service()
    s2 = get_embedding_service()

    assert s1 is s2
