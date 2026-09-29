"""Tests for Voyage embedding service: API calls, retries, and local fallback."""

import httpx
import pytest

from app.core.config import settings
from app.services import embeddings
from app.services.embeddings import (
    EmbeddingProviderError,
    LocalEmbeddingService,
    VoyageEmbeddingService,
    get_embedding_service,
)


def _voyage_response(items):
    return httpx.Response(
        200,
        json={"data": [{"index": i, "embedding": v} for i, v in enumerate(items)]},
        request=httpx.Request("POST", "https://api.voyageai.com/v1/embeddings"),
    )


def _make_service(key="test-key"):
    """Voyage service with a pre-registered httpx mock transport."""
    embeddings._embedding_service = None
    handler_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        handler_calls.append(request)
        if handler.respond_with is not None:
            return handler.respond_with
        return _voyage_response([[0.1, 0.2, 0.3]])

    handler.respond_with = None

    with embeddings.settings.__class__.env_editable if False else _patch_settings(
        VOYAGE_API_KEY=key
    ):
        svc = VoyageEmbeddingService()
        svc._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=httpx.Timeout(5.0),
            headers={"Authorization": f"Bearer {key}"},
        )
        svc._initialized = True
    svc._handler_calls = handler_calls
    svc._handler = handler
    return svc


class _patch_settings:
    """Temporarily patch attributes on the settings singleton."""

    def __init__(self, **overrides):
        self.overrides = overrides
        self._originals = {}

    def __enter__(self):
        for k, v in self.overrides.items():
            self._originals[k] = getattr(settings, k)
            setattr(settings, k, v)
        return self

    def __exit__(self, *exc):
        for k, v in self._originals.items():
            setattr(settings, k, v)


@pytest.fixture
def service():
    return _make_service()


@pytest.fixture(autouse=True)
def reset_singleton():
    embeddings._embedding_service = None
    yield
    embeddings._embedding_service = None


class TestVoyageEmbeddingService:
    @pytest.mark.asyncio
    async def test_embed_texts_batches_requests(self, service):
        """Three inputs with batch size 2 => two API calls, three vectors."""
        def per_batch_handler(request):
            import json

            service._handler_calls.append(request)
            body = json.loads(request.content)
            return _voyage_response([[float(len(b))] for b in body["input"]])

        service._client = httpx.AsyncClient(
            transport=httpx.MockTransport(per_batch_handler)
        )

        with _patch_settings(VOYAGE_BATCH_SIZE=2):
            service._batch_size = 2
            result = await service.embed_texts(["a", "b", "c"])

        assert result == [[1.0], [1.0], [1.0]]
        assert len(service._handler_calls) == 2

    @pytest.mark.asyncio
    async def test_embed_query_uses_query_input_type(self, service):
        service._handler.respond_with = _voyage_response([[0.4, 0.5]])

        result = await service.embed_query("what is ml")

        import json

        body = json.loads(service._handler_calls[0].content)
        assert result == [0.4, 0.5]
        assert body["input_type"] == "query"

    @pytest.mark.asyncio
    async def test_embed_texts_empty_input_no_api_call(self, service):
        result = await service.embed_texts([])

        assert result == []
        assert len(service._handler_calls) == 0

    @pytest.mark.asyncio
    async def test_retry_on_server_error_then_success(self, service):
        attempts = {"n": 0}

        def flaky_handler(request):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return httpx.Response(503, request=request)
            return _voyage_response([[0.7]])

        service._client = httpx.AsyncClient(transport=httpx.MockTransport(flaky_handler))
        with _patch_settings(VOYAGE_MAX_ATTEMPTS=3, VOYAGE_RETRY_BACKOFF=0.0):
            result = await service.embed_text("retry me")

        assert result == [0.7]
        assert attempts["n"] == 2

    @pytest.mark.asyncio
    async def test_permanent_error_raises_embedding_provider_error(self, service):
        service._handler.respond_with = httpx.Response(
            401,
            request=httpx.Request("POST", service._url),
        )

        with _patch_settings(VOYAGE_MAX_ATTEMPTS=2, VOYAGE_RETRY_BACKOFF=0.0):
            with pytest.raises(EmbeddingProviderError):
                await service._embed_batch(["x"], "document")

    @pytest.mark.asyncio
    async def test_api_failure_raises_embedding_provider_error(self, service):
        """On permanent API failure embed_text raises; callers decide fallback."""
        service._handler.respond_with = httpx.Response(
            401,
            request=httpx.Request("POST", service._url),
        )

        with _patch_settings(VOYAGE_MAX_ATTEMPTS=1):
            with pytest.raises(EmbeddingProviderError):
                await service.embed_text("no fallback")

    @pytest.mark.asyncio
    async def test_dimension_reports_configured_value(self, service):
        assert service.dimension == settings.VOYAGE_OUTPUT_DIMENSION

    def test_missing_api_key_falls_back_to_local(self):
        with _patch_settings(VOYAGE_API_KEY=""):
            svc = VoyageEmbeddingService()
            svc.initialize()

        assert svc.degraded is True
        assert isinstance(svc._fallback, LocalEmbeddingService)
        assert svc._client is None


class TestProviderSelection:
    def test_local_provider_selected_when_configured(self):
        with _patch_settings(EMBEDDING_PROVIDER="local"):
            svc = get_embedding_service()

        assert isinstance(svc, LocalEmbeddingService)

    def test_voyage_provider_selected_by_default(self):
        with _patch_settings(EMBEDDING_PROVIDER="voyage", VOYAGE_API_KEY="k" * 10):
            svc = get_embedding_service()

        assert isinstance(svc, VoyageEmbeddingService)
        assert svc.degraded is False
