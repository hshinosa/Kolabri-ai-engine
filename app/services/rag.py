"""
RAG Pipeline Service
====================
Combines vector search with LLM for context-aware responses.
Includes Policy Agent for retrieval optimization and pedagogical guardrails.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import math

from app.core.logging import get_logger
from app.core.guardrails import get_guardrails, GuardrailAction
from app.core.config import settings
from app.core.prompt_styles import GROUP_DISCUSSION_STYLE
from app.services.vector_store import get_vector_store, VectorStoreService
from app.services.llm import get_llm_service, OpenAILLMService, LLMResponse, ChatMessage
from app.services.efficiency_guard import get_efficiency_guard, EfficiencyGuard

logger = get_logger(__name__)


@dataclass
class RAGResult:
    """Result from RAG pipeline query."""
    answer: str
    sources: List[Dict[str, Any]]
    query: str
    tokens_used: int
    success: bool
    scaffolding_triggered: bool = False
    grounding_ratio: float = 1.0
    srl_phase: Optional[str] = None
    srl_sub_phase: Optional[str] = None
    error: Optional[str] = None
    processing_time_ms: float = 0


class RAGPipeline:
    """
    RAG (Retrieval-Augmented Generation) Pipeline with Policy-Based Optimization.
    
    Implements Policy Agent for retrieval optimization as described in research:
    - FETCH: Perform retrieval when context is needed
    - NO_FETCH: Skip retrieval for efficiency (greetings, follow-ups, simple queries)
    
    Workflow:
    1. Receive user query
    2. Policy decision: FETCH or NO_FETCH
    3. If FETCH: Search vector store for relevant documents
    4. Format context from retrieved documents
    5. Generate response using LLM with context
    6. Return answer with sources and action taken
    """
    
    # Skip retrieval patterns (greetings, acknowledgments, simple queries)
    SKIP_PATTERNS = [
        "halo", "hai", "hi", "hello", "terima kasih", "thanks", 
        "ok", "oke", "baik", "siap", "mantap", "good", "nice",
        "selamat pagi", "selamat siang", "selamat malam"
    ]
    
    # Minimum word count for substantive queries
    MIN_QUERY_WORDS = 3
    
    def __init__(
        self,
        vector_store: Optional[VectorStoreService] = None,
        llm_service: Optional[OpenAILLMService] = None,
        efficiency_guard: Optional[EfficiencyGuard] = None
    ):
        """
        Initialize RAG pipeline.
        
        Args:
            vector_store: Vector store service instance
            llm_service: LLM service instance
            efficiency_guard: Efficiency guard for caching and optimization
        """
        self.vector_store = vector_store or get_vector_store()
        self.llm_service = llm_service or get_llm_service()
        self.guardrails = get_guardrails()
        self.efficiency_guard = efficiency_guard or (
            get_efficiency_guard() if settings.ENABLE_EFFICIENCY_GUARD else None
        )
        
        # [OPTIMIZATION] Sequential semantic caching
        self._last_query: Optional[str] = None
        self._last_contexts: List[Dict[str, Any]] = []
        self._semantic_threshold = 0.85
        
        logger.info("rag_pipeline_initialized", efficiency_enabled=settings.ENABLE_EFFICIENCY_GUARD)

    async def _is_semantically_identical(self, query: str) -> bool:
        """Check if query is semantically similar to the previous one to reuse context."""
        if not self._last_query or not self._last_contexts:
            return False
        
        try:
            from app.services.embeddings import get_embedding_service

            embedder = get_embedding_service()
            v1 = await embedder.get_embedding(query)
            v2 = await embedder.get_embedding(self._last_query)

            dot_product = sum(a * b for a, b in zip(v1, v2))
            norm1 = math.sqrt(sum(a * a for a in v1))
            norm2 = math.sqrt(sum(b * b for b in v2))
            if norm1 == 0 or norm2 == 0:
                return False

            similarity = dot_product / (norm1 * norm2)
            return similarity > self._semantic_threshold
        except:
            return False
    
    def _should_retrieve(self, query: str, context_history: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Policy Agent: Decide whether to FETCH or NO_FETCH.
        
        Implements RL-based optimization strategy to reduce token usage and latency.
        Skip retrieval for:
        - Short queries (< MIN_QUERY_WORDS words)
        - Greetings and acknowledgments
        - Follow-up queries when context is already available
        
        Args:
            query: User query string
            context_history: Previous context for follow-up detection
            
        Returns:
            True for FETCH, False for NO_FETCH
        """
        query_lower = query.lower().strip()
        
        # Skip for greetings and simple acknowledgments
        if query_lower in self.SKIP_PATTERNS:
            logger.debug("policy_decision", action="NO_FETCH", reason="skip_pattern")
            return False
        
        # Skip for very short queries
        word_count = len(query.split())
        if word_count < self.MIN_QUERY_WORDS:
            logger.debug("policy_decision", action="NO_FETCH", reason="short_query")
            return False
        
        # Check for greeting patterns at start
        for pattern in self.SKIP_PATTERNS:
            if query_lower.startswith(pattern):
                # Only skip if query is primarily a greeting
                if word_count <= 5:
                    logger.debug("policy_decision", action="NO_FETCH", reason="greeting_prefix")
                    return False
        
        # FETCH for substantive queries
        logger.debug("policy_decision", action="FETCH", reason="substantive_query")
        return True
    
    async def query(
        self,
        query: str,
        collection_name: Optional[str] = None,
        n_results: int = 5,
        chat_history: Optional[List[ChatMessage]] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        fading_level: float = 0.0
    ) -> RAGResult:
        """
        Execute a RAG query with Policy-Based optimization, guardrails, and efficiency caching.
        
        Args:
            query: User question
            collection_name: Optional collection to search
            n_results: Number of documents to retrieve
            chat_history: Optional chat history for context
            filter_metadata: Optional metadata filter for search
            
        Returns:
            RAGResult with answer, sources, and action taken (FETCH/NO_FETCH)
        """
        start_time = datetime.now()
        
        # Build context for caching
        cache_context = {
            "collection_name": collection_name,
            "n_results": n_results,
            "filter_metadata": filter_metadata
        }
        
        # Define the query execution function
        async def execute_rag_query():
            try:
                # Step 0: Guardrails check - validate input
                guardrail_result = self.guardrails.check_input(query)
                
                if guardrail_result.action == GuardrailAction.BLOCK:
                    # Query blocked by guardrails
                    processing_time = (datetime.now() - start_time).total_seconds() * 1000
                    
                    logger.warning(
                        "rag_query_blocked",
                        reason=guardrail_result.reason,
                        query=query[:50]
                    )
                    
                    return RAGResult(
                        answer=guardrail_result.message or "Maaf, saya tidak bisa membantu dengan permintaan tersebut.",
                        sources=[],
                        query=query,
                        tokens_used=0,
                        success=True,  # Blocked but handled successfully
                        error=None,
                        processing_time_ms=processing_time
                    )
                
                # Use sanitized input if available
                safe_query = guardrail_result.sanitized_input or query
                
                # Step 1: Policy decision - FETCH or NO_FETCH
                should_fetch = self._should_retrieve(safe_query, self._last_contexts)
                action_taken = "FETCH" if should_fetch else "NO_FETCH"
                
                if not should_fetch:
                    # NO_FETCH: Skip retrieval, use LLM directly
                    logger.info(
                        "rag_policy_no_fetch",
                        query=safe_query[:100],
                        reason="policy_optimization"
                    )
                    
                    llm_response = await self.llm_service.generate(
                        prompt=query,
                        system_prompt="""Anda adalah asisten diskusi akademik Kolabri.
Berikan respons yang ramah, membantu, dan relevan untuk pertanyaan atau sapaan sederhana dalam konteks pembelajaran.
""" + GROUP_DISCUSSION_STYLE
                    )
                    
                    processing_time = (datetime.now() - start_time).total_seconds() * 1000
                    
                    return RAGResult(
                        answer=llm_response.content,
                        sources=[],
                        query=query,
                        tokens_used=llm_response.tokens_used,
                        success=llm_response.success,
                        error=llm_response.error,
                        processing_time_ms=processing_time
                    )
                
                # Step 1: FETCH - Search vector store (with semantic cache optimization)
                logger.info(
                    "rag_search_started",
                    query=query[:100],
                    collection=collection_name,
                    action=action_taken
                )
                
                # [OPTIMIZATION] Check if we can reuse previous context
                if await self._is_semantically_identical(query):
                    logger.info("rag_semantic_cache_hit", query=query[:50])
                    contexts = self._last_contexts
                    search_results = [] # Placeholder since we have contexts
                else:
                    search_results = await self.vector_store.search(
                        query=query,
                        collection_name=collection_name,
                        n_results=n_results,
                        where=filter_metadata
                    )
                    
                    if not search_results:
                        # No relevant documents found
                        logger.warning("rag_no_results", query=query[:100])
                        
                        # Generate response without context
                        llm_response = await self.llm_service.generate(
                            prompt=query,
                            system_prompt="""Anda adalah asisten diskusi akademik Kolabri.
Tidak ada dokumen relevan yang ditemukan untuk pertanyaan ini.
Berikan jawaban umum yang tetap membantu, jelaskan keterbatasannya dengan jujur, dan bila relevan sarankan untuk mengunggah dokumen yang sesuai.
""" + GROUP_DISCUSSION_STYLE
                        )
                        
                        processing_time = (datetime.now() - start_time).total_seconds() * 1000
                        
                        return RAGResult(
                            answer=llm_response.content,
                            sources=[],
                            query=query,
                            tokens_used=llm_response.tokens_used,
                            success=llm_response.success,
                            error=llm_response.error,
                            processing_time_ms=processing_time
                        )
                    
                    # Step 2: Format contexts & Update semantic cache
                    contexts = self._format_search_results(search_results)
                    self._last_query = query
                    self._last_contexts = contexts
                
                # Step 3: Generate response with RAG
                llm_response = await self.llm_service.generate_rag_response(
                    query=query,
                    contexts=contexts,
                    chat_history=chat_history,
                    fading_level=fading_level
                )
                
                # Step 3.5: Grounding Verification (TA Algorithm 1 OutputGuardrails)
                from app.services.grounding_verifier import get_grounding_verifier
                grounding_verifier = get_grounding_verifier()
                grounding_result = grounding_verifier.verify_grounding(
                    response=llm_response.content,
                    documents=[{"content": c.get("text", c.get("content", ""))} for c in contexts],
                    threshold=0.7
                )

                if not grounding_result.is_grounded:
                    logger.warning(
                        "grounding_check_failed",
                        ratio=grounding_result.grounding_ratio,
                        ungrounded=grounding_result.ungrounded_claims[:2]
                    )
                    return RAGResult(
                        answer="Jawaban tidak dapat diberikan tanpa berspekulasi di luar materi yang tersedia.",
                        sources=self._extract_sources(search_results) if search_results else [],
                        query=query,
                        tokens_used=llm_response.tokens_used,
                        success=True,
                        scaffolding_triggered=True,
                        processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000
                    )

                # Step 4: Output Guardrails (Pedagogy)
                output_check = self.guardrails.check_output(
                    response=llm_response.content,
                    original_query=query,
                    contexts=contexts
                )
                
                scaffolding_triggered = False
                if output_check.action == GuardrailAction.BLOCK:
                    return RAGResult(
                        answer=output_check.message,
                        sources=[],
                        query=query,
                        tokens_used=llm_response.tokens_used,
                        success=True,
                        scaffolding_triggered=True,
                        processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000
                    )
                elif output_check.action == GuardrailAction.REDIRECT:
                    # Reframe to Socratic
                    reframed = await self.llm_service.reframe_to_socratic(llm_response.content)
                    llm_response.content = reframed
                    scaffolding_triggered = True
                elif output_check.action == GuardrailAction.SANITIZE:
                    llm_response.content = output_check.sanitized_input

                # Step 5: Extract sources
                sources = self._extract_sources(search_results)
                
                processing_time = (datetime.now() - start_time).total_seconds() * 1000
                
                logger.info(
                    "rag_query_complete",
                    query=query[:100],
                    num_sources=len(sources),
                    processing_time_ms=processing_time
                )
                
                return RAGResult(
                    answer=llm_response.content,
                    sources=sources,
                    query=query,
                    tokens_used=llm_response.tokens_used,
                    success=llm_response.success,
                    scaffolding_triggered=scaffolding_triggered,
                    error=llm_response.error,
                    processing_time_ms=processing_time
                )
                
            except Exception as e:
                processing_time = (datetime.now() - start_time).total_seconds() * 1000
                
                logger.error(
                    "rag_query_failed",
                    error=str(e),
                    query=query[:100]
                )
                
                return RAGResult(
                    answer="",
                    sources=[],
                    query=query,
                    tokens_used=0,
                    success=False,
                    error=str(e),
                    processing_time_ms=processing_time
                )
        
        # Use Efficiency Guard if enabled
        if self.efficiency_guard:
            result_dict = await self.efficiency_guard.execute_with_caching(
                query=query,
                query_func=execute_rag_query,
                context=cache_context,
                ttl_seconds=settings.CACHE_TTL_SECONDS,
                use_deduplication=True
            )
            
            # Convert dict back to RAGResult if needed
            if isinstance(result_dict, dict):
                return RAGResult(**result_dict)
            return result_dict
        else:
            # Execute without caching
            return await execute_rag_query()
    
    async def query_with_course_context(
        self,
        query: str,
        course_id: str,
        chat_room_id: Optional[str] = None,
        n_results: int = 5
    ) -> RAGResult:
        """
        Query with course-specific context.
        
        Args:
            query: User question
            course_id: Course ID to filter documents
            chat_room_id: Optional chat room ID for additional context
            n_results: Number of results to retrieve
            
        Returns:
            RAGResult with course-specific answer
        """
        # Build metadata filter for course
        filter_metadata = {"course_id": course_id}
        
        # Use course-specific collection or default
        collection_name = f"course_{course_id}"
        
        return await self.query(
            query=query,
            collection_name=collection_name,
            n_results=n_results,
            filter_metadata=filter_metadata
        )
    
    async def get_similar_questions(
        self,
        query: str,
        collection_name: Optional[str] = None,
        n_results: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Find similar previously asked questions.
        
        Args:
            query: Current question
            collection_name: Collection to search
            n_results: Number of similar questions to return
            
        Returns:
            List of similar questions with their answers
        """
        try:
            # Search in Q&A collection
            qa_collection = collection_name or "qa_history"
            
            results = await self.vector_store.search(
                query=query,
                collection_name=qa_collection,
                n_results=n_results,
                where={"type": "question"}
            )
            
            similar = []
            for result in results:
                similar.append({
                    "question": result.get("content", ""),
                    "answer": result.get("metadata", {}).get("answer", ""),
                    "similarity": result.get("score", 0)
                })
            
            return similar
            
        except Exception as e:
            logger.warning(
                "similar_questions_failed",
                error=str(e)
            )
            return []
    
    def _format_search_results(
        self,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Format search results for LLM context."""
        contexts = []
        
        for result in results:
            contexts.append({
                "content": result.get("content", result.get("text", "")),
                "metadata": result.get("metadata", {}),
                "score": result.get("score", 0)
            })
        
        # Sort by score (higher is more relevant)
        contexts.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        return contexts

    def _build_multi_source_context(self, docs: List[Dict[str, Any]]) -> str:
        """Build context with explicit source attribution for multi-hop reasoning."""
        parts = []
        for i, doc in enumerate(docs, 1):
            source = doc.get("metadata", {}).get("source", f"Dokumen {i}")
            page = doc.get("metadata", {}).get("page", "")
            content = doc.get("content", doc.get("page_content", ""))
            header = f"[Sumber {i}: {source}"
            if page:
                header += f", hal. {page}"
            header += "]"
            parts.append(f"{header}\n{content}")
        return "\n\n---\n\n".join(parts)

    def _build_rag_token_prompt(self, query: str, context_docs: List[Dict[str, Any]]) -> str:
        """Build a prompt that instructs the LLM to synthesize across multiple sources."""
        context = self._build_multi_source_context(context_docs)
        return f"""Kamu adalah asisten pembelajaran yang membantu mahasiswa memahami materi.

INSTRUKSI PENTING:
- Jawab berdasarkan SEMUA sumber dokumen yang diberikan
- Sintesiskan informasi dari berbagai sumber (multi-hop reasoning)
- Jika jawaban memerlukan informasi dari beberapa dokumen, gabungkan secara koheren
- Jangan menjawab di luar konteks dokumen yang tersedia
- Gunakan pendekatan Socratic: bimbing mahasiswa untuk berpikir, bukan memberikan jawaban langsung

KONTEKS DOKUMEN:
{context}

PERTANYAAN MAHASISWA:
{query}

JAWABAN (sintesis dari semua sumber yang relevan):"""
    
    def _extract_sources(
        self,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Extract source information from search results."""
        sources = []
        seen_sources = set()
        
        for result in results:
            metadata = result.get("metadata", {})
            source = metadata.get("source", "Unknown")
            
            # Deduplicate sources
            if source not in seen_sources:
                seen_sources.add(source)
                sources.append({
                    "source": source,
                    "page": metadata.get("page"),
                    "chunk_index": metadata.get("chunk_index"),
                    "relevance_score": result.get("score", 0)
                })
        
        return sources


# Singleton instance
_rag_pipeline: Optional[RAGPipeline] = None


def get_rag_pipeline() -> RAGPipeline:
    """Get or create the RAG pipeline singleton."""
    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = RAGPipeline()
    return _rag_pipeline
