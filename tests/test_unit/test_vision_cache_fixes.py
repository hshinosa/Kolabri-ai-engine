"""
Tests untuk vision caption cache (M3: caption cache per content-hash).

Key = sha256(bytes JPEG persis yang dikirim ke provider + model + prompt).
- Panggilan identik -> HIT, vision dipanggil 1x.
- Bytes beda (konten/ukuran) -> MISS, vision dipanggil lagi.
- Redis error -> fail-open, ingest tetap jalan (vision dipanggil).
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.document_processing import image_extraction
from app.services.document_processing.image_extraction import (
    VISION_CAPTION_CACHE_TTL,
    generate_image_caption,
)


class StubImage:
    """Image-like dengan save() yang menulis bytes beda per konten.

    Penting: tests/conftest.py mengganti PIL dengan fake yang save()-nya
    selalu menulis bytes identik, jadi test beda-bytes tidak boleh
    bergantung pada PIL — stub ini menulis payload masing-masing image.
    """

    def __init__(self, payload: bytes, mode: str = "RGB"):
        self.payload = payload
        self.mode = mode

    def convert(self, mode):
        return StubImage(self.payload, mode)

    def save(self, fp, *args, **kwargs):
        fp.write(self.payload)

    def close(self):
        pass


class FakeRedisCache:
    """Fake RedisCache in-memory; broken=True meniru Redis mati/error."""

    def __init__(self, broken: bool = False):
        self.store = {}
        self.broken = broken
        self.get_calls = 0
        self.set_calls = 0
        self.ttls = []

    async def get(self, key):
        self.get_calls += 1
        if self.broken:
            raise RuntimeError("redis down")
        return self.store.get(key)

    async def set(self, key, value, ttl=3600, nx=False):
        self.set_calls += 1
        if self.broken:
            raise RuntimeError("redis down")
        self.store[key] = value
        self.ttls.append(ttl)
        return True


class FakeVisionClient:
    """Meniru vision_client.chat.completions.create(...) -> response."""

    def __init__(self, caption: str = "Deskripsi vision"):
        self.calls = 0
        self.caption = caption
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        message = SimpleNamespace(content=self.caption)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _fake_get_redis_cache(cache):
    async def _get():
        return cache

    return _get


def _raising_get_redis_cache():
    async def _get():
        raise RuntimeError("redis init failed")

    return _get


@pytest.mark.asyncio
async def test_identical_image_hits_cache_single_vision_call():
    cache = FakeRedisCache()
    client = FakeVisionClient(caption="Caption A")
    img = StubImage(b"identical-image-bytes")

    with patch.object(
        image_extraction, "get_redis_cache", new=_fake_get_redis_cache(cache)
    ):
        first = await generate_image_caption(img, vision_client=client)
        second = await generate_image_caption(img, vision_client=client)

    assert first == "Caption A"
    assert second == "Caption A"
    assert client.calls == 1
    assert cache.get_calls == 2
    assert cache.set_calls == 1
    assert cache.ttls == [VISION_CAPTION_CACHE_TTL]
    assert len(cache.store) == 1


@pytest.mark.asyncio
async def test_different_bytes_trigger_extra_vision_calls():
    cache = FakeRedisCache()
    client = FakeVisionClient(caption="Caption B")
    img_a = StubImage(b"image-a-payload")
    img_b = StubImage(b"image-b-payload")  # beda konten
    img_c = StubImage(b"image-a-payload" * 8)  # beda ukuran

    with patch.object(
        image_extraction, "get_redis_cache", new=_fake_get_redis_cache(cache)
    ):
        await generate_image_caption(img_a, vision_client=client)
        await generate_image_caption(img_b, vision_client=client)
        await generate_image_caption(img_c, vision_client=client)

    assert client.calls == 3
    assert len(cache.store) == 3


@pytest.mark.asyncio
async def test_redis_get_error_fail_open_vision_still_called():
    cache = FakeRedisCache(broken=True)
    client = FakeVisionClient(caption="Caption C")
    img = StubImage(b"broken-redis-image")

    with patch.object(
        image_extraction, "get_redis_cache", new=_fake_get_redis_cache(cache)
    ):
        first = await generate_image_caption(img, vision_client=client)
        second = await generate_image_caption(img, vision_client=client)

    # Redis error tidak boleh menggagalkan caption; vision tetap jalan.
    assert first == "Caption C"
    assert second == "Caption C"
    assert client.calls == 2
    assert cache.store == {}  # set juga gagal tanpa melempar


@pytest.mark.asyncio
async def test_get_redis_cache_raising_fail_open():
    client = FakeVisionClient(caption="Caption D")
    img = StubImage(b"raising-redis-image")

    with patch.object(
        image_extraction,
        "get_redis_cache",
        new=_raising_get_redis_cache(),
    ):
        result = await generate_image_caption(img, vision_client=client)

    assert result == "Caption D"
    assert client.calls == 1
