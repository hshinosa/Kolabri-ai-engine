"""
Optimized LLM Service dengan Connection Pooling
===============================================

Optimasi utama:
1. HTTP Connection Pooling - mengurangi overhead koneksi
2. Keep-Alive connections - reuse koneksi existing
3. Timeouts yang lebih optimal
4. Connection limits untuk mencegah overload

Issue: KOL-42 - Performance Optimization
"""

import asyncio
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError
from tenacity import retry, stop_after_attempt, wait_exponential
from app.core.config import settings
from app.core.logging import get_logger
from app.core.prompt_styles import GROUP_DISCUSSION_STYLE, GROUP_INTERVENTION_STYLE, SUMMARY_STYLE
import httpx

logger = get_logger(__name__)

# OPTIMIZATION: Connection pool settings
MAX_CONNECTIONS = 20          # Maksimum koneksi simultan
MAX_KEEPALIVE = 10            # Koneksi keep-alive
TIMEOUT_CONNECT = 5.0         # Timeout koneksi (detik)
TIMEOUT_READ = 60.0           # Timeout baca response (detik)
MAX_RETRIES = 3


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class LLMResponse:
    content: str
    tokens_used: int
    model: str
    success: bool
    error: Optional[str] = None
    response_time_ms: float = 0.0  # NEW: Track response time


class OptimizedLLMService:
    """
    LLM Service dengan connection pooling dan optimasi performa.
    
    Perubahan utama dari versi sebelumnya:
    - HTTP connection pooling via httpx.AsyncClient
    - Keep-alive connections untuk reuse
    - Connection limits untuk resource management
    - Timeouts yang lebih granular
    """
    
    SYSTEM_PROMPTS = {
        'default': 'Anda adalah asisten AI Kolabri yang membantu mahasiswa.',
        'rag': 'Anda adalah asisten diskusi akademik Kolabri. Bantu mahasiswa memahami materi dengan jawaban yang akurat, terstruktur, dan mendorong pemikiran kritis. ' + GROUP_DISCUSSION_STYLE,
        'intervention': 'Anda adalah fasilitator diskusi akademik Kolabri. ' + GROUP_INTERVENTION_STYLE,
        'summary': 'Anda adalah peringkas diskusi akademik Kolabri. ' + SUMMARY_STYLE,
    }
    
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise ValueError('OPENAI_API_KEY is required')
        
        # OPTIMIZATION: Create custom httpx client with connection pooling
        # Ini mengurangi overhead pembukaan koneksi baru untuk setiap request
        self._http_client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=MAX_CONNECTIONS,
                max_keepalive_connections=MAX_KEEPALIVE,
            ),
            timeout=httpx.Timeout(
                connect=TIMEOUT_CONNECT,
                read=TIMEOUT_READ,
                write=10.0,
                pool=5.0
            ),
            http2=True,  # Enable HTTP/2 untuk multiplexing
        )
        
        # Pass custom http_client ke AsyncOpenAI
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            http_client=self._http_client,
            max_retries=MAX_RETRIES,
        )
        
        self.model = settings.OPENAI_MODEL
        self.temperature = 0.0
        self.max_tokens = 1000
        
        logger.info(
            "optimized_llm_service_initialized",
            max_connections=MAX_CONNECTIONS,
            keepalive=MAX_KEEPALIVE,
            timeout_connect=TIMEOUT_CONNECT,
            timeout_read=TIMEOUT_READ
        )
    
    async def close(self):
        """Close HTTP client - panggil saat shutdown."""
        await self._http_client.aclose()
        logger.info("llm_service_http_client_closed")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=lambda e: isinstance(e, (APIConnectionError, RateLimitError))
    )
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        track_timing: bool = True
    ) -> LLMResponse:
        """
        Generate text dengan connection pooling dan circuit breaker protection.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt (optional)
            context: RAG context (optional)
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            track_timing: Whether to track response time
            
        Returns:
            LLMResponse dengan timing information
        """
        import time
        
        # KOL-135: Circuit Breaker Integration
        circuit_breaker = get_llm_circuit_breaker()
        
        start_time = time.time()
        
        full_system = system_prompt or self.SYSTEM_PROMPTS['default']
        if context:
            full_system = self.SYSTEM_PROMPTS['rag'].format(context=context)
        
        messages = [
            {'role': 'system', 'content': full_system},
            {'role': 'user', 'content': prompt}
        ]
        
        try:
            # Execute with circuit breaker
            async def _call_llm():
                resp = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature or self.temperature,
                    max_tokens=max_tokens or self.max_tokens,
                )
                
                content = resp.choices[0].message.content or ''
                tokens = resp.usage.total_tokens if resp.usage else 0
                
                return content, tokens
            
            content, tokens = await circuit_breaker.call(_call_llm)
            
            response_time = (time.time() - start_time) * 1000
            
            if track_timing:
                logger.info(
                    "llm_generation_completed",
                    model=self.model,
                    tokens_used=tokens,
                    response_time_ms=round(response_time, 2)
                )
            
            return LLMResponse(
                content=content,
                tokens_used=tokens,
                model=self.model,
                success=True,
                response_time_ms=response_time
            )
            
        except CircuitBreakerOpenError:
            response_time = (time.time() - start_time) * 1000
            logger.warning("llm_circuit_breaker_open_returning_fallback")
            return LLMResponse(
                content="Maaf, AI Assistant sedang unavailable. Silakan coba beberapa saat lagi.",
                tokens_used=0,
                model="fallback",
                success=False,
                error="Circuit breaker open - LLM service unavailable",
                response_time_ms=response_time
            )
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            logger.error(
                'llm_generation_failed',
                error=str(e),
                response_time_ms=round(response_time, 2)
            )
            raise e
    
    async def generate_rag_response(
        self,
        query: str,
        contexts: List[Dict[str, Any]],
        chat_history: Optional[List[ChatMessage]] = None,
        fading_level: float = 0.0
    ) -> LLMResponse:
        """
        Generate RAG response dengan scaffolding level.
        
        OPTIMIZATION: Jika contexts kosong, gunakan direct generation
        untuk menghemat waktu formatting.
        """
        instr = self._get_scaffolding_instruction(fading_level)
        
        # OPTIMIZATION: Skip context formatting jika kosong
        if contexts:
            ctx_text = self._format_contexts(contexts)
            prompt = f'Konteks:\n{ctx_text}\n\nPertanyaan: {query}\n\nInstruksi: {instr}'
        else:
            prompt = f'Pertanyaan: {query}\n\nInstruksi: {instr}'
        
        return await self.generate(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPTS['rag']
        )
    
    def _get_scaffolding_instruction(self, fading_level: float) -> str:
        """Get scaffolding instruction berdasarkan fading level."""
        if fading_level < settings.SCAFFOLDING_FULL_THRESHOLD:
            return 'Berikan jawaban lengkap dengan penjelasan detail.'
        elif fading_level < settings.SCAFFOLDING_MINIMAL_THRESHOLD:
            return 'Berikan jawaban dengan hints Socratic.'
        return 'Berikan minimal hints saja, dorong mahasiswa berpikir mandiri.'
    
    async def generate_intervention(
        self,
        messages: List[Dict[str, Any]],
        intervention_type: str = 'redirect',
        topic: Optional[str] = None
    ) -> LLMResponse:
        """Generate intervention message."""
        # OPTIMIZATION: Limit context window untuk kecepatan
        recent_messages = messages[-10:] if len(messages) > 10 else messages
        text = '\n'.join([
            f"{m.get('sender', 'User')}: {m.get('content', '')}"
            for m in recent_messages
        ])
        
        prompt = f'Tipe intervensi: {intervention_type}\nTopic: {topic or "N/A"}\n\nPesan:\n{text}'
        
        return await self.generate(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPTS['intervention'],
            max_tokens=500  # Shorter for interventions
        )
    
    async def generate_summary(
        self,
        messages: List[Dict[str, Any]],
        include_action_items: bool = True
    ) -> LLMResponse:
        """Generate discussion summary."""
        text = '\n'.join([
            f"{m.get('sender', 'User')}: {m.get('content', '')}"
            for m in messages
        ])
        
        action_prompt = " Sertakan action items." if include_action_items else ""
        prompt = f'Ringkasan diskusi:{action_prompt}\n\n{text}'
        
        return await self.generate(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPTS['summary'],
            max_tokens=800
        )
    
    async def reframe_to_socratic(self, response: str) -> str:
        """Reframe response ke format Socratic."""
        try:
            reframed = await self.generate(
                prompt=f'Ubah menjadi pertanyaan Socratic: {response}',
                max_tokens=500
            )
            return reframed.content if reframed.success else response
        except:
            return response
    
    async def get_goal_refinement_suggestion(
        self,
        current_goal: str,
        missing_criteria: List[str]
    ) -> LLMResponse:
        """Get goal refinement suggestion."""
        criteria_text = ', '.join(missing_criteria)
        prompt = f'Goal: {current_goal}\nKriteria yang kurang: {criteria_text}'
        
        return await self.generate(prompt=prompt, max_tokens=600)
    
    def _format_contexts(self, contexts: List[Dict[str, Any]]) -> str:
        """Format contexts untuk prompt."""
        if not contexts:
            return "Tidak ada konteks yang relevan."
        
        # OPTIMIZATION: Limit jumlah contexts untuk kecepatan
        max_contexts = 5
        contexts = contexts[:max_contexts]
        
        return '\n\n'.join([
            f"[{i+1}] {c.get('content', '')}"
            for i, c in enumerate(contexts)
        ])
    
    def _format_chat_history(self, history: List[ChatMessage]) -> str:
        """Format chat history."""
        # OPTIMIZATION: Limit history untuk kecepatan
        recent_history = history[-5:] if len(history) > 5 else history
        
        return '\n'.join([
            f"{'User' if m.role == 'user' else 'AI'}: {m.content}"
            for m in recent_history
        ])


# Global singleton instance with lazy initialization
_llm_service = None


def get_llm_service() -> OptimizedLLMService:
    """Get singleton instance of OptimizedLLMService."""
    global _llm_service
    if _llm_service is None:
        _llm_service = OptimizedLLMService()
    return _llm_service


async def close_llm_service():
    """Close LLM service - panggil saat application shutdown."""
    global _llm_service
    if _llm_service:
        await _llm_service.close()
        _llm_service = None
        logger.info("llm_service_closed")
