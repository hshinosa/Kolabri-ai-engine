from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import reranker as reranker_module
from app.services.reranker import CrossEncoderReranker, get_reranker


@pytest.fixture(autouse=True)
def reset_reranker_singleton():
    reranker_module._reranker = None
    yield
    reranker_module._reranker = None


def _docs():
    return [
        {"id": 1, "content": "doc one"},
        {"id": 2, "content": "doc two"},
        {"id": 3, "content": "doc three"},
    ]


def test_init_enabled_when_setting_and_library_available():
    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", True),
        patch.object(
            reranker_module,
            "CROSS_ENCODER_AVAILABLE",
            True,
        ),
    ):
        instance = CrossEncoderReranker(top_k=2, retrieve_k=5)

    assert instance.enabled is True
    assert instance.model is None
    assert instance.top_k == 2
    assert instance.retrieve_k == 5


def test_init_disabled_when_library_missing():
    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", True),
        patch.object(
            reranker_module,
            "CROSS_ENCODER_AVAILABLE",
            False,
        ),
    ):
        instance = CrossEncoderReranker()

    assert instance.enabled is False


@pytest.mark.asyncio
async def test_load_model_lazy_loads_cross_encoder_once():
    mock_model = MagicMock()

    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", True),
        patch.object(
            reranker_module,
            "CROSS_ENCODER_AVAILABLE",
            True,
        ),
        patch.object(reranker_module.settings, "RERANK_CACHE_DIR", ""),
        patch.object(
            reranker_module, "TextCrossEncoder", return_value=mock_model, create=True
        ) as text_cross_encoder,
    ):
        instance = CrossEncoderReranker(model_name="my-model")
        await instance.load_model()
        await instance.load_model()

    assert instance.model is mock_model
    text_cross_encoder.assert_called_once()


@pytest.mark.asyncio
async def test_rerank_returns_original_subset_when_disabled():
    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", False),
        patch.object(
            reranker_module,
            "CROSS_ENCODER_AVAILABLE",
            True,
        ),
    ):
        instance = CrossEncoderReranker(top_k=2)

    documents = _docs()
    result = await instance.rerank("query", documents)

    assert result == documents[:2]


@pytest.mark.asyncio
async def test_rerank_disabled_respects_explicit_top_k_override():
    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", False),
        patch.object(
            reranker_module,
            "CROSS_ENCODER_AVAILABLE",
            True,
        ),
    ):
        instance = CrossEncoderReranker(top_k=3)

    result = await instance.rerank("query", _docs(), top_k=1)

    assert result == _docs()[:1]


@pytest.mark.asyncio
async def test_rerank_returns_empty_list_for_empty_documents():
    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", True),
        patch.object(
            reranker_module,
            "CROSS_ENCODER_AVAILABLE",
            True,
        ),
    ):
        instance = CrossEncoderReranker()

    result = await instance.rerank("query", [])

    assert result == []


@pytest.mark.asyncio
async def test_rerank_sorts_by_score_and_adds_metadata():
    mock_model = MagicMock()
    mock_model.rerank.return_value = [0.1, 0.9, 0.5]

    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", True),
        patch.object(
            reranker_module,
            "CROSS_ENCODER_AVAILABLE",
            True,
        ),
    ):
        instance = CrossEncoderReranker(model_name="ce-model", top_k=2)
        instance.model = mock_model
        documents = _docs()

        result = await instance.rerank("search query", documents)

    assert [doc["id"] for doc in result] == [2, 3]
    assert result[0]["rerank_score"] == 0.9
    assert result[0]["rerank_model"] == "ce-model"
    assert "rerank_score" not in documents[0]
    assert instance.total_reranks == 1


@pytest.mark.asyncio
async def test_rerank_respects_explicit_top_k_override():
    mock_model = MagicMock()
    mock_model.rerank.return_value = [0.1, 0.9, 0.5]

    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", True),
        patch.object(
            reranker_module,
            "CROSS_ENCODER_AVAILABLE",
            True,
        ),
    ):
        instance = CrossEncoderReranker(model_name="ce-model", top_k=3)
        instance.model = mock_model

        result = await instance.rerank("search query", _docs(), top_k=1)

    assert [doc["id"] for doc in result] == [2]


@pytest.mark.asyncio
async def test_rerank_uses_cache_on_second_call():
    mock_model = MagicMock()
    mock_model.rerank.return_value = [0.2, 0.6, 0.4]

    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", True),
        patch.object(
            reranker_module,
            "CROSS_ENCODER_AVAILABLE",
            True,
        ),
    ):
        instance = CrossEncoderReranker(top_k=2)
        instance.model = mock_model
        documents = _docs()

        first = await instance.rerank("query", documents)
        second = await instance.rerank("query", documents)

    assert first == second
    assert instance.cache_hits == 1
    assert instance.total_reranks == 1
    mock_model.rerank.assert_called_once()


@pytest.mark.asyncio
async def test_rerank_calls_load_model_when_model_missing():
    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", True),
        patch.object(
            reranker_module,
            "CROSS_ENCODER_AVAILABLE",
            True,
        ),
    ):
        instance = CrossEncoderReranker(top_k=1)
        loaded_model = MagicMock()
        loaded_model.rerank.return_value = [0.8, 0.2, 0.1]

        async def fake_load_model():
            instance.model = loaded_model

        with patch.object(
            instance, "load_model", new=AsyncMock(side_effect=fake_load_model)
        ) as load_mock:
            result = await instance.rerank("query", _docs())

    load_mock.assert_awaited_once()
    assert result[0]["id"] == 1


@pytest.mark.asyncio
async def test_rerank_falls_back_to_original_order_on_exception():
    broken_model = MagicMock()
    broken_model.rerank.side_effect = RuntimeError("rerank failed")

    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", True),
        patch.object(
            reranker_module,
            "CROSS_ENCODER_AVAILABLE",
            True,
        ),
    ):
        instance = CrossEncoderReranker(top_k=2)
        instance.model = broken_model
        documents = _docs()

        result = await instance.rerank("query", documents)

    assert result == documents[:2]
    assert instance.total_reranks == 0


def test_get_metrics_reports_cache_rate_and_average_time():
    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", True),
        patch.object(
            reranker_module,
            "CROSS_ENCODER_AVAILABLE",
            True,
        ),
    ):
        instance = CrossEncoderReranker()

    instance.model = MagicMock()
    instance.total_reranks = 4
    instance.cache_hits = 2
    instance.avg_rerank_time_ms = 12.3456

    metrics = instance.get_metrics()

    assert metrics["enabled"] is True
    assert metrics["model_loaded"] is True
    assert metrics["cache_hit_rate"] == 0.5
    assert metrics["avg_rerank_time_ms"] == 12.35


def test_disable_turns_off_reranking():
    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", True),
        patch.object(
            reranker_module,
            "CROSS_ENCODER_AVAILABLE",
            True,
        ),
    ):
        instance = CrossEncoderReranker()

    instance.disable()

    assert instance.enabled is False


def test_enable_turns_on_reranking_when_library_available():
    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", False),
        patch.object(
            reranker_module,
            "CROSS_ENCODER_AVAILABLE",
            True,
        ),
    ):
        instance = CrossEncoderReranker()

        instance.enable()

    assert instance.enabled is True


def test_enable_does_not_turn_on_when_library_missing():
    with (
        patch.object(reranker_module.settings, "ENABLE_RERANKING", True),
        patch.object(
            reranker_module,
            "CROSS_ENCODER_AVAILABLE",
            False,
        ),
    ):
        instance = CrossEncoderReranker()
        instance.enable()

        assert instance.enabled is False


def test_get_reranker_returns_singleton_with_settings_values():
    with (
        patch.object(reranker_module.settings, "RERANK_MODEL_NAME", "configured-model"),
        patch.object(
            reranker_module.settings,
            "RERANK_TOP_K",
            4,
        ),
        patch.object(reranker_module.settings, "RERANK_RETRIEVE_K", 11),
    ):
        first = get_reranker()
        second = get_reranker()

    assert first is second
    assert first.model_name == "configured-model"
    assert first.top_k == 4
    assert first.retrieve_k == 11
