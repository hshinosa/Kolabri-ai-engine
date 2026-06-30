import httpx
from typing import Optional, Dict, Any
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis_cache import get_redis_cache

logger = get_logger(__name__)

PROVIDER_CACHE_KEY = "kolabri:provider:active"
PROVIDER_CACHE_TTL = 300


class ProviderRepository:
    def __init__(self):
        self.core_api_url = settings.CORE_API_URL
        self.internal_secret = settings.CORE_API_SECRET
        self.timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

    async def get_active_provider(self) -> Optional[Dict[str, Any]]:
        try:
            redis_cache = await get_redis_cache()
            cached = await redis_cache.get(PROVIDER_CACHE_KEY)
            if cached:
                logger.info("provider_cache_hit")
                return cached
        except Exception:
            logger.exception("provider_cache_get_failed")

        provider = await self._fetch_from_core_api()

        if provider:
            try:
                redis_cache = await get_redis_cache()
                await redis_cache.set(
                    PROVIDER_CACHE_KEY, provider, ttl=PROVIDER_CACHE_TTL
                )
                logger.info("provider_cached", ttl=PROVIDER_CACHE_TTL)
            except Exception:
                logger.exception("provider_cache_set_failed")

        return provider

    async def _fetch_from_core_api(self) -> Optional[Dict[str, Any]]:
        endpoint = f"{self.core_api_url}/api/internal/ai-provider/active"
        headers = {"X-Internal-Secret": self.internal_secret}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(endpoint, headers=headers)

                if response.status_code == 404:
                    logger.warning("no_active_provider_in_database")
                    return None

                if response.status_code == 401:
                    logger.error("provider_fetch_unauthorized")
                    return None

                response.raise_for_status()
                data = response.json()

                provider_data = data.get("data")
                if not provider_data:
                    logger.warning("provider_response_empty")
                    return None

                logger.info(
                    "provider_fetched_successfully",
                    provider_name=provider_data.get("name"),
                )
                return self._transform_to_provider_context(provider_data)

        except httpx.TimeoutException:
            logger.error("provider_fetch_timeout", endpoint=endpoint)
            return None
        except httpx.HTTPError as e:
            logger.exception("provider_fetch_http_error", error=str(e))
            return None
        except Exception:
            logger.exception("provider_fetch_unexpected_error")
            return None

    def _transform_to_provider_context(
        self, provider: Dict[str, Any]
    ) -> Dict[str, Any]:
        config = provider.get("config", {})

        return {
            "auth": {"credential": provider.get("apiKey")},
            "execution": {
                "baseUrl": provider.get("baseUrl"),
                "model": config.get("defaultModel"),
                "temperature": config.get("temperature"),
                "maxTokens": config.get("maxTokens"),
            },
        }


_provider_repository: Optional[ProviderRepository] = None


async def get_provider_repository() -> ProviderRepository:
    global _provider_repository
    if _provider_repository is None:
        _provider_repository = ProviderRepository()
    return _provider_repository


async def invalidate_provider_cache():
    try:
        redis_cache = await get_redis_cache()
        await redis_cache.delete(PROVIDER_CACHE_KEY)
        logger.info("provider_cache_invalidated")
    except Exception:
        logger.exception("provider_cache_invalidation_failed")
