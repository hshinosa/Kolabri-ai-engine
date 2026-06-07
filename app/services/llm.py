import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.core.config import settings
from app.core.logging import get_logger
from app.core.prompt_templates import (
    SYSTEM_RAG, SYSTEM_PERSONAL_CHAT, SYSTEM_INTERVENTION, SYSTEM_SUMMARY,
    SYSTEM_SOCRATIC, SYSTEM_GOAL_VALIDATION, SYSTEM_GOAL_REFINEMENT,
    RAG_FEW_SHOT, COT_RAG_TEMPLATE, COT_RAG_WITH_HISTORY,
    COT_INTERVENTION_TEMPLATE, COT_SUMMARY_TEMPLATE,
    COT_GOAL_VALIDATION, COT_GOAL_REFINEMENT, TEMPERATURE,
)
from app.services.circuit_breaker import (
    CircuitBreakerOpenError,
    get_llm_circuit_breaker,
)
import httpx

logger = get_logger(__name__)

MAX_CONNECTIONS = 50
MAX_KEEPALIVE = 20


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
        'default': SYSTEM_PERSONAL_CHAT,
        'rag': SYSTEM_RAG,
        'intervention': SYSTEM_INTERVENTION,
        'summary': SYSTEM_SUMMARY,
        'socratic': SYSTEM_SOCRATIC,
        'goal_validation': SYSTEM_GOAL_VALIDATION,
        'goal_refinement': SYSTEM_GOAL_REFINEMENT,
    }
    
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required")
        self._http_client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=MAX_CONNECTIONS,
                max_keepalive_connections=MAX_KEEPALIVE,
            ),
            timeout=httpx.Timeout(
                connect=settings.LLM_TIMEOUT_CONNECT_SECONDS,
                read=settings.LLM_TIMEOUT_READ_SECONDS,
                write=10.0,
                pool=5.0
            ),
            http2=True,
        )
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            http_client=self._http_client,
            max_retries=settings.LLM_MAX_RETRIES,
        )
        self.model = settings.OPENAI_MODEL
        self.temperature = settings.OPENAI_TEMPERATURE
        self.max_tokens = settings.OPENAI_MAX_TOKENS

    async def close(self):
        await self._http_client.aclose()

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        full_system = system_prompt or self.SYSTEM_PROMPTS["default"]
        if context:
            full_system += f"\n\nKonteks tambahan:\n{context}"

        messages = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": prompt},
        ]

        breaker = get_llm_circuit_breaker()
        start = time.time()
        try:
            result = await breaker.call(
                self._execute_with_retry,
                messages,
                temperature or self.temperature,
                max_tokens or self.max_tokens,
            )
            result.response_time_ms = (time.time() - start) * 1000
            return result
        except CircuitBreakerOpenError:
            elapsed = (time.time() - start) * 1000
            retry_after = max(1, int(breaker.recovery_timeout))
            logger.warning(
                "llm_degraded_breaker_open",
                retry_after=retry_after,
                response_time_ms=round(elapsed, 2),
            )
            raise LLMDegradedError(
                reason="llm_circuit_open", retry_after=retry_after
            )
        except (RateLimitError, APIConnectionError, APIError) as exc:
            elapsed = (time.time() - start) * 1000
            logger.warning(
                "llm_degraded_retry_exhausted",
                error=str(exc),
                response_time_ms=round(elapsed, 2),
            )
            raise LLMDegradedError(
                reason="llm_retry_exhausted",
                retry_after=settings.LLM_RETRY_DEFAULT_RETRY_AFTER_SECONDS,
            )
        except Exception:
            elapsed = (time.time() - start) * 1000
            logger.exception("llm_generation_failed", response_time_ms=round(elapsed, 2))
            return LLMResponse(
                content="", tokens_used=0, model=self.model, success=False,
                error="Internal error", response_time_ms=elapsed
            )

    @retry(
        stop=stop_after_attempt(settings.LLM_MAX_RETRIES),
        wait=wait_exponential(
            multiplier=0.01 if settings.ENV == "testing" else settings.LLM_RETRY_DELAY_MULTIPLIER,
            min=0.01 if settings.ENV == "testing" else settings.LLM_RETRY_DELAY_BASE,
        ),
        retry=retry_if_exception_type((RateLimitError, APIConnectionError))
        | retry_if_exception_type(APIError),
        reraise=True,
    )
    async def _execute_with_retry(self, messages, temperature, max_tokens):
        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content or ""
            tokens = resp.usage.total_tokens if resp.usage else 0
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
            logger.exception("llm_generation_failed")
            return LLMResponse(
                content="", tokens_used=0, model=self.model, success=False, error="Internal error"
            )

    async def generate_rag_response(
        self,
        query: str,
        contexts: List[Dict[str, Any]],
        chat_history: Optional[List[ChatMessage]] = None,
        fading_level: float = 0.0,
    ) -> LLMResponse:
        ctx_text = self._format_contexts(contexts)
        system_prompt = self.SYSTEM_PROMPTS["rag"] + "\n\n" + RAG_FEW_SHOT

        if chat_history:
            history_text = self._format_chat_history(chat_history)
            prompt = COT_RAG_WITH_HISTORY.format(
                history=history_text, contexts=ctx_text, query=query
            )
        else:
            prompt = COT_RAG_TEMPLATE.format(contexts=ctx_text, query=query)

        return await self.generate(
            prompt=prompt, system_prompt=system_prompt,
            temperature=TEMPERATURE["rag"]
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
            prompt=prompt, system_prompt=self.SYSTEM_PROMPTS["intervention"],
            temperature=TEMPERATURE["intervention"]
        )

    async def generate_summary(
        self, messages: List[Dict[str, Any]], include_action_items: bool = True
    ) -> LLMResponse:
        messages_text = "\n".join(
            f"{m.get('sender', 'User')}: {m.get('content', '')}" for m in messages
        )
        prompt = COT_SUMMARY_TEMPLATE.format(messages=messages_text)
        return await self.generate(
            prompt=prompt, system_prompt=self.SYSTEM_PROMPTS["summary"],
            temperature=TEMPERATURE["summary"]
        )

    async def reframe_to_socratic(self, response: str) -> str:
        prompt = f"Jawaban langsung yang perlu diubah:\n{response}\n\nBuat 2-3 pertanyaan Socratic bertahap yang mengarah ke jawaban tersebut."
        result = await self.generate(
            prompt=prompt, system_prompt=self.SYSTEM_PROMPTS["socratic"],
            temperature=TEMPERATURE["socratic"]
        )
        return result.content if result.success else response

    async def get_goal_refinement_suggestion(
        self, current_goal: str, missing_criteria: List[str]
    ) -> LLMResponse:
        prompt = COT_GOAL_REFINEMENT.format(
            current_goal=current_goal,
            missing_criteria=", ".join(missing_criteria)
        )
        return await self.generate(
            prompt=prompt, system_prompt=self.SYSTEM_PROMPTS["goal_refinement"],
            temperature=TEMPERATURE["goal_refinement"]
        )

    def _format_contexts(self, contexts: List[Dict[str, Any]]) -> str:
        """Format retrieved contexts for the prompt."""
        return "\n\n".join(
            [
                f"[{i+1}] Sumber: {c.get('metadata', {}).get('source', 'Unknown')} (Halaman {c.get('metadata', {}).get('page', '?')})\n{c.get('content', '')}"
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

def get_llm_service():
    global _llm_service
    if _llm_service is None:
        _llm_service = OpenAILLMService()
    return _llm_service

async def close_llm_service():
    global _llm_service
    if _llm_service:
        await _llm_service.close()
        _llm_service = None
