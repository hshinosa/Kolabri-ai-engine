import asyncio
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.core.config import settings
from app.core.logging import get_logger
from app.core.prompt_styles import GROUP_DISCUSSION_STYLE, GROUP_INTERVENTION_STYLE, SUMMARY_STYLE

logger = get_logger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_BASE = 1.0
RETRY_DELAY_MULTIPLIER = 2.0

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

class OpenAILLMService:
    SYSTEM_PROMPTS = {
        'default': 'Anda adalah asisten AI Kolabri yang membantu mahasiswa.',
        'rag': 'Anda adalah asisten diskusi akademik Kolabri. ' + GROUP_DISCUSSION_STYLE,
        'intervention': 'Anda adalah fasilitator diskusi akademik Kolabri. ' + GROUP_INTERVENTION_STYLE,
        'summary': 'Anda adalah peringkas diskusi akademik Kolabri. ' + SUMMARY_STYLE
    }
    
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required")
        self.client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL
        )
        self.model = settings.OPENAI_MODEL
        self.temperature = settings.OPENAI_TEMPERATURE
        self.max_tokens = settings.OPENAI_MAX_TOKENS

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        context: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Core generation method with retry logic."""
        full_system = system_prompt or self.SYSTEM_PROMPTS["default"]
        if context:
            full_system += f"\n\nKonteks tambahan:\n{context}"

        messages = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": prompt},
        ]

        try:
            return await self._execute_with_retry(
                messages, temperature or self.temperature, max_tokens or self.max_tokens
            )
        except Exception as e:
            logger.error("llm_generation_failed", error=str(e))
            return LLMResponse(
                content="", tokens_used=0, model=self.model, success=False, error=str(e)
            )

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(
            multiplier=0.01 if settings.ENV == "testing" else RETRY_DELAY_MULTIPLIER,
            min=0.01 if settings.ENV == "testing" else RETRY_DELAY_BASE,
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
            logger.error("llm_generation_failed", error=str(e))
            return LLMResponse(
                content="", tokens_used=0, model=self.model, success=False, error=str(e)
            )

    async def generate_rag_response(
        self,
        query: str,
        contexts: List[Dict[str, Any]],
        chat_history: Optional[List[ChatMessage]] = None,
        fading_level: float = 0.0,
    ) -> LLMResponse:
        """Generate a RAG-enhanced response with scaffolding instructions."""
        instr = self._get_scaffolding_instruction(fading_level)
        ctx_text = self._format_contexts(contexts)

        system_prompt = self.SYSTEM_PROMPTS["rag"]
        if chat_history:
            history_text = self._format_chat_history(chat_history)
            prompt = f"Riwayat Diskusi:\n{history_text}\n\nKonteks:\n{ctx_text}\n\nPertanyaan: {query}\n\nInstruksi: {instr}"
        else:
            prompt = f"Konteks:\n{ctx_text}\n\nPertanyaan: {query}\n\nInstruksi: {instr}"

        return await self.generate(prompt=prompt, system_prompt=system_prompt)

    def _get_scaffolding_instruction(self, fading_level: float) -> str:
        """Get instruction based on fading level (fading-out scaffolding)."""
        if fading_level < settings.SCAFFOLDING_FULL_THRESHOLD:
            return "Berikan panduan langkah-demi-langkah yang sangat mendetail."
        elif fading_level < settings.SCAFFOLDING_MINIMAL_THRESHOLD:
            return "Berikan petunjuk umum (hint) tanpa memberikan jawaban langsung."
        else:
            return "Gunakan teknik Socratic Questioning untuk membimbing mahasiswa menemukan jawabannya sendiri."

    async def generate_intervention(
        self,
        chat_messages: List[Dict[str, Any]],
        intervention_type: str = "redirect",
        topic: Optional[str] = None,
    ) -> LLMResponse:
        """Generate a proactive intervention message."""
        text = "\n".join(
            [
                f"{m.get('sender', 'User')}: {m.get('content', '')}"
                for m in chat_messages[-10:]
            ]
        )
        prompt = f"Tipe Intervensi: {intervention_type}\nTopik: {topic or 'Umum'}\n\nDiskusi Terakhir:\n{text}"
        return await self.generate(
            prompt=prompt, system_prompt=self.SYSTEM_PROMPTS["intervention"]
        )

    async def generate_summary(
        self, messages: List[Dict[str, Any]], include_action_items: bool = True
    ) -> LLMResponse:
        """Generate a summary of the discussion."""
        text = "\n".join(
            [f"{m.get('sender', 'User')}: {m.get('content', '')}" for m in messages]
        )
        prompt = f"Ringkas diskusi berikut ini. {'Sertakan action items.' if include_action_items else ''}\n\nDiskusi:\n{text}"
        return await self.generate(
            prompt=prompt, system_prompt=self.SYSTEM_PROMPTS["summary"]
        )

    async def reframe_to_socratic(self, response: str) -> str:
        """Reframe a direct answer into a Socratic questioning hint."""
        prompt = f"Ubah jawaban berikut menjadi pertanyaan Socratic yang membimbing: {response}"
        result = await self.generate(
            prompt=prompt, system_prompt="Anda adalah ahli Socratic questioning."
        )
        return result.content if result.success else response

    async def get_goal_refinement_suggestion(
        self, current_goal: str, missing_criteria: List[str]
    ) -> LLMResponse:
        """Generate suggestions to refine a student's learning goal."""
        criteria_list = ", ".join(missing_criteria)
        prompt = f"Goal saat ini: {current_goal}\nKriteria SMART yang kurang: {criteria_list}\n\nBantu mahasiswa memperbaiki goal ini dengan pertanyaan pemandu."
        return await self.generate(prompt=prompt)

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

_llm_service = None
def get_llm_service():
    global _llm_service
    if _llm_service is None: _llm_service = OpenAILLMService()
    return _llm_service
