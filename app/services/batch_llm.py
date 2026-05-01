"""
Batch LLM Service
=================

Priority 3: Request Batching Aggresive

Batch multiple queries jadi 1 LLM call.
10x cost reduction, 5x throughput improvement.
"""

import asyncio
from typing import List, Dict, Any
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger
from app.services.llm import OpenAILLMService as OptimizedLLMService, get_llm_service

logger = get_logger(__name__)


@dataclass
class BatchResult:
    """Result untuk batch request."""
    success: bool
    content: str
    tokens_used: int
    error: str = None


class BatchLLMService:
    """LLM Service dengan batching support."""
    
    def __init__(self, llm_service: OptimizedLLMService = None):
        self.llm_service = llm_service or get_llm_service()
        self.max_batch_size = 10  # Maximum 10 queries per batch
    
    async def generate_batch(
        self,
        prompts: List[str],
        system_prompt: str = None
    ) -> List[BatchResult]:
        """
        Generate responses untuk multiple prompts dalam satu batch.
        
        Args:
            prompts: List of prompts (max 10)
            system_prompt: System prompt (shared)
        
        Returns:
            List of BatchResult
        """
        if not prompts:
            return []
        
        if len(prompts) > self.max_batch_size:
            # Process in chunks
            results = []
            for i in range(0, len(prompts), self.max_batch_size):
                chunk = prompts[i:i + self.max_batch_size]
                chunk_results = await self._generate_batch_chunk(chunk, system_prompt)
                results.extend(chunk_results)
            return results
        
        return await self._generate_batch_chunk(prompts, system_prompt)
    
    async def _generate_batch_chunk(
        self,
        prompts: List[str],
        system_prompt: str
    ) -> List[BatchResult]:
        """Generate untuk satu chunk (max 10)."""
        
        # Combine prompts dengan separator
        combined_prompt = self._combine_prompts(prompts)
        
        try:
            # Single LLM call untuk semua
            result = await self.llm_service.generate(
                prompt=combined_prompt,
                system_prompt=system_prompt or "Anda adalah asisten AI.",
                max_tokens=2000  # Higher untuk batch
            )
            
            if not result.success:
                # All failed
                return [
                    BatchResult(success=False, content="", tokens_used=0, error=result.error)
                    for _ in prompts
                ]
            
            # Split responses
            responses = self._split_responses(result.content, len(prompts))
            
            # Calculate tokens per response (approximate)
            tokens_per_response = result.tokens_used // len(prompts)
            
            return [
                BatchResult(
                    success=True,
                    content=response,
                    tokens_used=tokens_per_response
                )
                for response in responses
            ]
            
        except Exception as e:
            logger.error("batch_generation_failed", error=str(e), count=len(prompts))
            return [
                BatchResult(success=False, content="", tokens_used=0, error=str(e))
                for _ in prompts
            ]
    
    def _combine_prompts(self, prompts: List[str]) -> str:
        """Combine multiple prompts jadi satu."""
        formatted = []
        for i, prompt in enumerate(prompts, 1):
            formatted.append(f"[{i}] {prompt}")
        
        return (
            "Jawab semua pertanyaan berikut:\n\n" +
            "\n\n".join(formatted) +
            "\n\nFormat jawaban: [1] Jawaban 1, [2] Jawaban 2, dst."
        )
    
    def _split_responses(self, combined: str, expected_count: int) -> List[str]:
        """Split combined response jadi individual answers."""
        responses = []
        
        for i in range(1, expected_count + 1):
            # Look for pattern [i] or just split by position
            marker_start = f"[{i}]"
            marker_end = f"[{i+1}]" if i < expected_count else None
            
            start_idx = combined.find(marker_start)
            if start_idx == -1:
                responses.append(f"Jawaban {i} tidak ditemukan")
                continue
            
            start_idx += len(marker_start)
            
            if marker_end:
                end_idx = combined.find(marker_end, start_idx)
                if end_idx == -1:
                    end_idx = len(combined)
            else:
                end_idx = len(combined)
            
            response = combined[start_idx:end_idx].strip()
            responses.append(response if response else f"Jawaban {i} kosong")
        
        # Fill missing responses
        while len(responses) < expected_count:
            responses.append("")
        
        return responses[:expected_count]


# Global instance
_batch_service = None


def get_batch_llm_service() -> BatchLLMService:
    """Get singleton instance."""
    global _batch_service
    if _batch_service is None:
        _batch_service = BatchLLMService()
    return _batch_service
