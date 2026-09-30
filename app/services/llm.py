import asyncio
import hashlib
import json
import time
import weakref
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError
from cachetools import TTLCache
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    retry_if_exception,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.utils.sensitive_data import sanitize_error_message
from app.core.prompt_templates import (
    SYSTEM_RAG,
    SYSTEM_PERSONAL_CHAT,
    SYSTEM_INTERVENTION,
    SYSTEM_SUMMARY,
    SYSTEM_SOCRATIC,
    SYSTEM_GOAL_VALIDATION,
    SYSTEM_GOAL_REFINEMENT,
    RAG_FEW_SHOT,
    COT_RAG_TEMPLATE,
    COT_RAG_WITH_HISTORY,
    COT_INTERVENTION_TEMPLATE,
    COT_SUMMARY_TEMPLATE,
    COT_GOAL_REFINEMENT,
    TEMPERATURE,
)
from app.services.circuit_breaker import (
    CircuitBreakerOpenError,
    get_llm_circuit_breaker,
)
from app.services.repositories.provider_repository import get_provider_repository
import httpx

logger = get_logger(__name__)

MAX_CONNECTIONS = 50
MAX_KEEPALIVE = 20

# M2/M4: provider-response cache at the single generate() boundary.
# Responses and single-flight locks are scoped to the running event loop:
# asyncio.Lock is loop-bound, and production serves requests from a single
# loop, so the cache is effectively process-wide while staying safe under
# per-loop test runners. Gated by settings.ENABLE_EFFICIENCY_GUARD.
PROVIDER_CACHE_TTL_SECONDS = 600
PROVIDER_CACHE_MAX_ENTRIES = 1000

# Sentinel: distinguishes "usage object lacks the attribute" from "attribute is None".
_USAGE_MISSING = object()


class _ProviderCallCache:
    """Per-event-loop response cache + single-flight locks for generate()."""

    def __init__(self) -> None:
        self.responses: TTLCache = TTLCache(
            maxsize=PROVIDER_CACHE_MAX_ENTRIES, ttl=PROVIDER_CACHE_TTL_SECONDS
        )
        self.inflight: Dict[str, asyncio.Lock] = {}


_provider_call_caches: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _ProviderCallCache]" = (
    weakref.WeakKeyDictionary()
)


def _get_provider_call_cache() -> _ProviderCallCache:
    loop = asyncio.get_running_loop()
    cache = _provider_call_caches.get(loop)
    if cache is None:
        cache = _ProviderCallCache()
        _provider_call_caches[loop] = cache
    return cache


class LLMDegradedError(Exception):
    """Raised when LLM service is degraded: circuit open or retries exhausted."""

    def __init__(self, reason: str, retry_after: int):
        super().__init__(f"LLM degraded: {reason}")
        self.reason = reason
        self.retry_after = retry_after


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class LLMResponse:
    """LLM call result.

    Note: ``error`` field contains user-safe messages only. Internal exception
    details are logged via ``logger.exception(...)`` and never exposed in this
    field. Route handlers may safely propagate ``error`` to clients.
    """

    content: str
    tokens_used: int
    model: str
    success: bool
    error: Optional[str] = None
    response_time_ms: float = 0.0


class OpenAILLMService:
    SYSTEM_PROMPTS = {
        "default": SYSTEM_PERSONAL_CHAT,
        "rag": SYSTEM_RAG,
        "intervention": SYSTEM_INTERVENTION,
        "summary": SYSTEM_SUMMARY,
        "socratic": SYSTEM_SOCRATIC,
        "goal_validation": SYSTEM_GOAL_VALIDATION,
        "goal_refinement": SYSTEM_GOAL_REFINEMENT,
    }

    def __init__(self, provider_context: Optional[Dict[str, Any]] = None):
        self._provider_context = provider_context
        self._http_client = None
        self.client = None
        self.model = None
        self.temperature = None
        self.max_tokens = None

        # Eager configure when provider_context is given or unified provider is off.
        # UNIFIED mode stays lazy until ensure_ready() fetches provider (or env fallback).
        # Offline eval scripts should set UNIFIED_PROVIDER_ENABLED=false.
        if provider_context is not None or not settings.UNIFIED_PROVIDER_ENABLED:
            self._configure(provider_context)

    def _configure(self, provider_context: Optional[Dict[str, Any]] = None):
        auth = provider_context.get("auth", {}) if provider_context else {}
        execution = provider_context.get("execution", {}) if provider_context else {}

        api_key = auth.get("credential") or settings.OPENAI_API_KEY
        base_url = execution.get("baseUrl") or settings.OPENAI_BASE_URL
        model = execution.get("model") or settings.OPENAI_MODEL
        temperature = execution.get("temperature")
        max_tokens = execution.get("maxTokens")

        if not api_key:
            raise ValueError("OPENAI_API_KEY is required")

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                limits=httpx.Limits(
                    max_connections=MAX_CONNECTIONS,
                    max_keepalive_connections=MAX_KEEPALIVE,
                ),
                timeout=httpx.Timeout(
                    connect=settings.LLM_TIMEOUT_CONNECT_SECONDS,
                    read=settings.LLM_TIMEOUT_READ_SECONDS,
                    write=10.0,
                    pool=5.0,
                ),
                http2=True,
            )

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=self._http_client,
            max_retries=0,  # PERF-AI-02: Disable SDK retries, let tenacity handle all retries
        )
        self.model = model
        self.temperature = (
            temperature if temperature is not None else settings.OPENAI_TEMPERATURE
        )
        self.max_tokens = (
            max_tokens if max_tokens is not None else settings.OPENAI_MAX_TOKENS
        )
        self._provider_context = provider_context

    async def ensure_ready(self):
        if self.client is not None:
            return

        provider_context = self._provider_context
        if provider_context is None and settings.UNIFIED_PROVIDER_ENABLED:
            provider_context = await self._fetch_provider_from_database()

        self._configure(provider_context)

    async def _fetch_provider_from_database(self) -> Optional[Dict[str, Any]]:
        try:
            provider_repo = await get_provider_repository()
            provider_context = await provider_repo.get_active_provider()

            if provider_context:
                logger.info("provider_fetched_from_database")
                return provider_context

            logger.warning("no_active_provider_fallback_to_env")
            return None

        except Exception:
            logger.exception("provider_fetch_failed_fallback_to_env")
            return None

    async def close(self):
        if self._http_client is not None:
            await self._http_client.aclose()

    def _provider_cache_key(
        self, messages: List[Dict[str, str]], temperature, max_tokens
    ) -> str:
        """SHA-256 over every input that determines the provider response.

        Covers the spec key components (prompt + system prompt incl. injected
        context + model + temperature + max_tokens) via the serialized messages,
        plus chat_history and base_url so two requests can only share a cached
        response when they would have produced the same provider call.
        """
        material = {
            "messages": messages,
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "base_url": str(self.client.base_url),
        }
        digest = hashlib.sha256(
            json.dumps(
                material, sort_keys=True, ensure_ascii=False, default=str
            ).encode("utf-8")
        )
        return digest.hexdigest()

    def _log_prompt_cache_usage(self, usage) -> bool:
        """M0: report provider prefix-cache token usage when the provider sends it."""
        if usage is None:
            return False
        hit = getattr(usage, "prompt_cache_hit_tokens", _USAGE_MISSING)
        miss = getattr(usage, "prompt_cache_miss_tokens", _USAGE_MISSING)
        if hit is _USAGE_MISSING and miss is _USAGE_MISSING:
            return False
        logger.info(
            "llm_prompt_cache_usage",
            hit=None if hit is _USAGE_MISSING else hit,
            miss=None if miss is _USAGE_MISSING else miss,
            model=self.model,
        )
        return True

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        chat_history: Optional[List[ChatMessage]] = None,
    ) -> LLMResponse:
        full_system = system_prompt or self.SYSTEM_PROMPTS["default"]
        if context:
            full_system += f"\n\nKonteks tambahan:\n{context}"

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": full_system},
        ]
        if chat_history:
            for m in chat_history[-10:]:
                messages.append(
                    {
                        "role": m.role if m.role in ("user", "assistant") else "user",
                        "content": m.content,
                    }
                )
        messages.append({"role": "user", "content": prompt})

        await self.ensure_ready()
        effective_temperature = (
            self.temperature if temperature is None else temperature
        )
        effective_max_tokens = self.max_tokens if max_tokens is None else max_tokens

        # M2/M4: efficiency guard off -> no provider-response caching at all.
        if not settings.ENABLE_EFFICIENCY_GUARD:
            return await self._execute_via_provider(
                messages, effective_temperature, effective_max_tokens
            )

        key = self._provider_cache_key(
            messages, effective_temperature, effective_max_tokens
        )
        call_cache = _get_provider_call_cache()

        cached = call_cache.responses.get(key)
        if cached is not None:
            logger.info("llm_provider_cache", result="hit", model=self.model)
            return cached

        lock = call_cache.inflight.get(key)
        if lock is None:
            lock = asyncio.Lock()
            call_cache.inflight[key] = lock
        async with lock:
            try:
                # Single-flight re-check: an identical concurrent request may
                # have populated the cache while we waited for the lock.
                cached = call_cache.responses.get(key)
                if cached is not None:
                    logger.info("llm_provider_cache", result="hit", model=self.model)
                    return cached
                result = await self._execute_via_provider(
                    messages, effective_temperature, effective_max_tokens
                )
                # Only successful responses are cached; failures and exceptions
                # never enter the cache.
                if result.success:
                    call_cache.responses[key] = result
                logger.info(
                    "llm_provider_cache",
                    result="miss",
                    success=result.success,
                    model=self.model,
                )
                return result
            finally:
                # Drop only our own lock so a successor's lock is never removed.
                if call_cache.inflight.get(key) is lock:
                    del call_cache.inflight[key]

    async def _execute_via_provider(self, messages, temperature, max_tokens):
        """Provider call behind circuit breaker + retry (M2/M4 cache boundary)."""
        breaker = get_llm_circuit_breaker()
        start = time.time()
        try:
            result = await breaker.call(
                self._execute_with_retry,
                messages,
                temperature,
                max_tokens,
            )
            result.response_time_ms = (time.time() - start) * 1000
            return result
        except CircuitBreakerOpenError as err:
            elapsed = (time.time() - start) * 1000
            retry_after = max(1, int(breaker.recovery_timeout))
            logger.warning(
                "llm_degraded_breaker_open",
                retry_after=retry_after,
                response_time_ms=round(elapsed, 2),
            )
            raise LLMDegradedError(
                reason="llm_circuit_open", retry_after=retry_after
            ) from err
        except (RateLimitError, APIConnectionError, APIError) as exc:
            elapsed = (time.time() - start) * 1000
            logger.warning(
                "llm_degraded_retry_exhausted",
                error=sanitize_error_message(str(exc)),
                response_time_ms=round(elapsed, 2),
            )
            raise LLMDegradedError(
                reason="llm_retry_exhausted",
                retry_after=settings.LLM_RETRY_DEFAULT_RETRY_AFTER_SECONDS,
            ) from exc
        except Exception as exc:
            elapsed = (time.time() - start) * 1000
            logger.error(
                "llm_generation_failed",
                response_time_ms=round(elapsed, 2),
                error=sanitize_error_message(str(exc)),
            )
            return LLMResponse(
                content="",
                tokens_used=0,
                model=self.model,
                success=False,
                error="Internal error",
                response_time_ms=elapsed,
            )

    @retry(
        stop=stop_after_attempt(settings.LLM_MAX_RETRIES),
        wait=wait_exponential(
            multiplier=0.01
            if settings.ENV == "testing"
            else settings.LLM_RETRY_DELAY_MULTIPLIER,
            min=0.01 if settings.ENV == "testing" else settings.LLM_RETRY_DELAY_BASE,
        ),
        retry=retry_if_exception_type((RateLimitError, APIConnectionError))
        | retry_if_exception(
            lambda e: isinstance(e, APIError) and getattr(e, "status_code", 0) >= 500
        ),
        reraise=True,
    )
    async def _execute_with_retry(self, messages, temperature, max_tokens):
        try:
            logger.info(
                "llm_request",
                model=self.model,
                message_count=len(messages),
                temperature=temperature,
                max_tokens=max_tokens,
            )
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content or ""
            tokens = resp.usage.total_tokens if resp.usage else 0
            logger.info(
                "llm_response",
                content_length=len(content),
                content_preview=content[:100] if content else None,
                tokens_used=tokens,
                finish_reason=resp.choices[0].finish_reason if resp.choices else None,
            )
            self._log_prompt_cache_usage(resp.usage)
            return LLMResponse(
                content=content, tokens_used=tokens, model=self.model, success=True
            )
        except Exception as e:
            # Only retry on rate limits, connection issues, or 5xx server errors
            if isinstance(e, (RateLimitError, APIConnectionError)) or (
                isinstance(e, APIError) and getattr(e, "status_code", 0) >= 500
            ):
                raise e
            # Log and return failure for other errors (no retry)
            logger.error("llm_generation_failed", error=sanitize_error_message(str(e)))
            return LLMResponse(
                content="",
                tokens_used=0,
                model=self.model,
                success=False,
                error="Internal error",
            )

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        chat_history: Optional[List[ChatMessage]] = None,
    ):
        """Async generator yielding content chunks (str) via stream=True.

        PERF-AI-01: Streaming path for NO_FETCH queries (greetings, short follow-ups).
        Bypasses tenacity/circuit-breaker — streaming is fire-and-forget; caller
        handles errors. Cannot retry after partial yield. NO_FETCH path is low-risk
        (no grounding at stake). See design.md PERF-AI-01 Layer 1.
        """
        full_system = system_prompt or self.SYSTEM_PROMPTS["default"]
        if context:
            full_system += f"\n\nKonteks tambahan:\n{context}"
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": full_system},
        ]
        if chat_history:
            for m in chat_history[-10:]:
                messages.append(
                    {
                        "role": m.role if m.role in ("user", "assistant") else "user",
                        "content": m.content,
                    }
                )
        messages.append({"role": "user", "content": prompt})
        await self.ensure_ready()
        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature if temperature is None else temperature,
                max_tokens=self.max_tokens if max_tokens is None else max_tokens,
                stream=True,
            )
            usage_reported = False
            async for chunk in stream:
                if not usage_reported:
                    # M0: providers put prefix-cache usage on the final chunk.
                    usage_reported = self._log_prompt_cache_usage(
                        getattr(chunk, "usage", None)
                    )
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            logger.error("llm_stream_failed", error=sanitize_error_message(str(e)))
            raise

    async def generate_rag_response(
        self,
        query: str,
        contexts: List[Dict[str, Any]],
        chat_history: Optional[List[ChatMessage]] = None,
        fading_level: float = 0.0,
        context: Optional[str] = None,
    ) -> LLMResponse:
        ctx_text = self._format_contexts(contexts)
        system_prompt = self.SYSTEM_PROMPTS["rag"] + "\n\n" + RAG_FEW_SHOT

        # Add scaffolding context to system prompt if provided
        if context:
            system_prompt += f"\n\n{context}"

        if chat_history:
            history_text = self._format_chat_history(chat_history)
            prompt = COT_RAG_WITH_HISTORY.format(
                history=history_text, contexts=ctx_text, query=query
            )
        else:
            prompt = COT_RAG_TEMPLATE.format(contexts=ctx_text, query=query)

        return await self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=TEMPERATURE["rag"],
            chat_history=chat_history,
        )

    async def generate_intervention(
        self,
        chat_messages: List[Dict[str, Any]],
        intervention_type: str = "redirect",
        topic: Optional[str] = None,
    ) -> LLMResponse:
        messages_text = "\n".join(
            f"{m.get('sender', 'User')}: {m.get('content', '')}"
            for m in chat_messages[-10:]
        )
        prompt = COT_INTERVENTION_TEMPLATE.format(
            topic=topic or "Umum",
            intervention_type=intervention_type,
            messages=messages_text,
        )
        return await self.generate(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPTS["intervention"],
            temperature=TEMPERATURE["intervention"],
        )

    async def generate_summary(
        self, messages: List[Dict[str, Any]], include_action_items: bool = True
    ) -> LLMResponse:
        messages_text = "\n".join(
            f"{m.get('sender', 'User')}: {m.get('content', '')}" for m in messages
        )
        prompt = COT_SUMMARY_TEMPLATE.format(messages=messages_text)
        return await self.generate(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPTS["summary"],
            temperature=TEMPERATURE["summary"],
        )

    async def reframe_to_socratic(self, response: str) -> str:
        prompt = f"Jawaban langsung yang perlu diubah:\n{response}\n\nBuat 2-3 pertanyaan Socratic bertahap yang mengarah ke jawaban tersebut."
        result = await self.generate(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPTS["socratic"],
            temperature=TEMPERATURE["socratic"],
        )
        return result.content if result.success else response

    async def get_goal_refinement_suggestion(
        self, current_goal: str, missing_criteria: List[str]
    ) -> LLMResponse:
        prompt = COT_GOAL_REFINEMENT.format(
            current_goal=current_goal, missing_criteria=", ".join(missing_criteria)
        )
        return await self.generate(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPTS["goal_refinement"],
            temperature=TEMPERATURE["goal_refinement"],
        )

    def _format_contexts(self, contexts: List[Dict[str, Any]]) -> str:
        """Format retrieved contexts for the prompt."""
        return "\n\n".join(
            [
                f"[{i + 1}] Sumber: {c.get('metadata', {}).get('source', 'Unknown')} (Halaman {c.get('metadata', {}).get('page', '?')})\n{c.get('content', '')}"
                for i, c in enumerate(contexts)
            ]
        )

    def _format_chat_history(self, history: List[ChatMessage]) -> str:
        """Format chat history for contextual understanding."""
        return "\n".join(
            [
                f"{'Mahasiswa' if m.role == 'user' else 'Asisten'}: {m.content}"
                for m in history[-5:]
            ]
        )


OptimizedLLMService = OpenAILLMService

_llm_service = None


def get_llm_service(provider_context: Optional[Dict[str, Any]] = None):
    """Return shared LLM service (singleton) unless a one-off provider context is given."""
    global _llm_service
    if provider_context is not None:
        return OpenAILLMService(provider_context=provider_context)
    if _llm_service is None:
        _llm_service = OpenAILLMService()
    return _llm_service


async def close_llm_service():
    global _llm_service
    if _llm_service:
        await _llm_service.close()
        _llm_service = None
