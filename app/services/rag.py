"""
RAG Pipeline Service
====================
Combines vector search with LLM for context-aware responses.
Includes Policy Agent for retrieval optimization and pedagogical guardrails.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import math

from app.core.logging import get_logger
from app.core.guardrails import get_guardrails, GuardrailAction
from app.core.config import settings
from app.core.prompt_templates import (
    SYSTEM_PERSONAL_CHAT,
    SYSTEM_RAG_NO_CONTEXT,
    TEMPERATURE,
)
from app.core.prompt_styles import SCAFFOLDING_EARLY_STYLE, SCAFFOLDING_LATE_STYLE
from app.services.vector_store import get_vector_store, VectorStoreService
from app.services.reranker import get_reranker, CrossEncoderReranker
from app.services.rag_quality import RetrievalQualityControls
from app.services.llm import get_llm_service, OpenAILLMService, ChatMessage
from app.services.efficiency_guard import get_efficiency_guard, EfficiencyGuard

logger = get_logger(__name__)

ProviderContext = Dict[str, Any]


@dataclass
class RAGResult:
    """Result from RAG pipeline query.

    Note: ``error`` field contains user-safe messages only. Internal exception
    details are logged via ``logger.exception(...)`` and never exposed in this
    field. Route handlers may safely propagate ``error`` to clients.
    """

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
    outcome: Optional[str] = None
    reason: Optional[str] = None
    citations: List[Dict[str, Any]] = field(default_factory=list)


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
        "halo",
        "hai",
        "hi",
        "hello",
        "terima kasih",
        "thanks",
        "ok",
        "oke",
        "baik",
        "siap",
        "mantap",
        "good",
        "nice",
        "selamat pagi",
        "selamat siang",
        "selamat malam",
    ]

    # Minimum word count for substantive queries
    MIN_QUERY_WORDS = 3

    def __init__(
        self,
        vector_store: Optional[VectorStoreService] = None,
        llm_service: Optional[OpenAILLMService] = None,
        efficiency_guard: Optional[EfficiencyGuard] = None,
        reranker: Optional[CrossEncoderReranker] = None,
        quality_controls: Optional[RetrievalQualityControls] = None,
        provider_context: Optional[ProviderContext] = None,
    ):
        """
        Initialize RAG pipeline.

        Args:
            vector_store: Vector store service instance
            llm_service: LLM service instance
            efficiency_guard: Efficiency guard for caching and optimization
        """
        self.vector_store = vector_store or get_vector_store()
        self.llm_service = llm_service or get_llm_service(
            provider_context=provider_context
        )
        self.guardrails = get_guardrails()
        self.quality_controls = (
            quality_controls or RetrievalQualityControls.from_settings()
        )
        self.reranker = reranker or get_reranker()
        self.efficiency_guard = efficiency_guard or (
            get_efficiency_guard() if settings.ENABLE_EFFICIENCY_GUARD else None
        )

        # [OPTIMIZATION] Sequential semantic caching
        self._last_query: Optional[str] = None
        self._last_contexts: List[Dict[str, Any]] = []
        self._semantic_threshold = self.quality_controls.semantic_cache_threshold
        self._grounding_threshold = self.quality_controls.grounding_threshold

        logger.info(
            "rag_pipeline_initialized",
            efficiency_enabled=settings.ENABLE_EFFICIENCY_GUARD,
        )

    async def _is_semantically_identical(self, query: str) -> bool:
        """Check if query is semantically similar to the previous one to reuse context."""
        if not self._last_query or not self._last_contexts:
            return False

        try:
            from app.services.embeddings import get_embedding_service

            embedder = get_embedding_service()
            v1 = await embedder.get_embedding(query)
            # PERF-AI-06: Reuse cached embedding of last query instead of re-embedding
            v2 = getattr(self, "_last_query_embedding", None)
            if v2 is None:
                v2 = await embedder.get_embedding(self._last_query)
                self._last_query_embedding = v2

            dot_product = sum(a * b for a, b in zip(v1, v2))
            norm1 = math.sqrt(sum(a * a for a in v1))
            norm2 = math.sqrt(sum(b * b for b in v2))
            if norm1 == 0 or norm2 == 0:
                return False

            similarity = dot_product / (norm1 * norm2)
            return similarity > self._semantic_threshold
        except:
            return False

    def _should_retrieve(
        self, query: str, context_history: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
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
                    logger.debug(
                        "policy_decision", action="NO_FETCH", reason="greeting_prefix"
                    )
                    return False

        # FETCH for substantive queries
        logger.debug("policy_decision", action="FETCH", reason="substantive_query")
        return True

    def _answer_from_week_context(
        self, query: str, week_context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        if week_context is None:
            return None

        raw_titles = week_context.get("material_titles")
        if not isinstance(raw_titles, list):
            return None

        titles = [
            title.strip()
            for title in raw_titles
            if isinstance(title, str) and title.strip()
        ]
        if not titles:
            return None

        query_lower = query.lower()
        asks_materials = "materi" in query_lower and any(
            phrase in query_lower
            for phrase in (
                "apa aja",
                "apa saja",
                "apa yang",
                "di sesi",
                "sesi ini",
                "di sini",
                "disini",
                "repository",
                "dokumen",
            )
        )
        if not asks_materials:
            return None

        raw_week_title = week_context.get("week_title")
        week_title = (
            raw_week_title.strip()
            if isinstance(raw_week_title, str) and raw_week_title.strip()
            else "sesi ini"
        )
        formatted_titles = "\n".join(f"- {title}" for title in titles[:10])
        remaining = len(titles) - 10
        suffix = f"\n- ...dan {remaining} materi lainnya" if remaining > 0 else ""
        return (
            f"Materi yang tersedia untuk {week_title}:\n"
            f"{formatted_titles}{suffix}\n\n"
            "Menurut kamu, dari daftar ini materi mana yang paling perlu dibahas dulu oleh kelompok?"
        )

    async def query(
        self,
        query: str,
        collection_name: Optional[str] = None,
        n_results: int = 5,
        chat_history: Optional[List[ChatMessage]] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        fading_level: float = 0.0,
        score_threshold: Optional[float] = None,
        guardrail_context: Optional[Dict[str, Any]] = None,
        session_week_index: Optional[int] = None,
        max_week_index: Optional[int] = None,
        week_context: Optional[Dict[str, Any]] = None,
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

        week_context_answer = self._answer_from_week_context(query, week_context)
        if week_context_answer is not None:
            return RAGResult(
                answer=week_context_answer,
                sources=[],
                query=query,
                tokens_used=0,
                success=True,
                processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                outcome="week_context",
                reason="material_list_query",
            )

        from app.services.week_rag import (
            rank_week_boosted_results,
            sources_to_citations,
            week_metadata_filter,
        )

        effective_filter = filter_metadata
        week_cap = week_metadata_filter(max_week_index)
        if week_cap:
            effective_filter = {**(filter_metadata or {}), **week_cap}

        # Build context for caching
        cache_context = {
            "collection_name": collection_name,
            "n_results": n_results,
            "filter_metadata": effective_filter,
            "score_threshold": score_threshold,
            "has_chat_history": bool(chat_history),
            "history_length": len(chat_history) if chat_history else 0,
        }

        # Define the query execution function
        async def execute_rag_query():
            try:
                guardrail_result = self.guardrails.check_input(query, guardrail_context)
                from app.core.guardrail_diagnostics import log_guardrail_decision

                log_guardrail_decision(
                    guardrail_result, surface="input", route="rag.execute_query"
                )

                if guardrail_result.action == GuardrailAction.BLOCK:
                    processing_time = (
                        datetime.now() - start_time
                    ).total_seconds() * 1000

                    logger.warning(
                        "rag_query_blocked",
                        reason=guardrail_result.reason,
                        query=query[:50],
                    )

                    triggered = guardrail_result.triggered_rules or []
                    rule_id = (
                        triggered[0]
                        if triggered
                        else (guardrail_result.reason or "guarded")
                    )
                    return RAGResult(
                        answer=guardrail_result.message
                        or "Maaf, saya tidak bisa membantu dengan permintaan tersebut.",
                        sources=[],
                        query=query,
                        tokens_used=0,
                        success=True,
                        error=None,
                        processing_time_ms=processing_time,
                        outcome="guarded",
                        reason=rule_id,
                    )

                # Use sanitized input if available
                safe_query = guardrail_result.sanitized_input or query

                # Query rewriting: enrich short follow-up queries with chat history context
                search_query = safe_query
                if chat_history and len(safe_query.split()) <= 6:
                    last_assistant = None
                    for msg in reversed(chat_history):
                        if msg.role == "assistant":
                            last_assistant = msg.content
                            break
                    if last_assistant:
                        topic_hint = last_assistant[:200]
                        search_query = (
                            f"{safe_query} (konteks sebelumnya: {topic_hint})"
                        )
                        logger.info(
                            "rag_query_rewritten",
                            original=safe_query[:80],
                            rewritten=search_query[:120],
                        )

                # Step 1: Policy decision - FETCH or NO_FETCH
                should_fetch = self._should_retrieve(search_query, self._last_contexts)
                action_taken = "FETCH" if should_fetch else "NO_FETCH"

                if not should_fetch:
                    logger.info(
                        "rag_policy_no_fetch",
                        query=safe_query[:100],
                        reason="policy_optimization",
                    )

                    no_fetch_prompt = query
                    if chat_history:
                        history_lines = [
                            f"{'Mahasiswa' if m.role == 'user' else 'Asisten'}: {m.content}"
                            for m in chat_history[-5:]
                        ]
                        history_text = "\n".join(history_lines)
                        no_fetch_prompt = f"Riwayat percakapan:\n{history_text}\n\nPertanyaan terbaru mahasiswa: {query}"

                    llm_response = await self.llm_service.generate(
                        prompt=no_fetch_prompt,
                        system_prompt=SYSTEM_PERSONAL_CHAT,
                        temperature=TEMPERATURE["personal_chat"],
                        chat_history=chat_history,
                    )

                    processing_time = (
                        datetime.now() - start_time
                    ).total_seconds() * 1000

                    return RAGResult(
                        answer=llm_response.content,
                        sources=[],
                        query=query,
                        tokens_used=llm_response.tokens_used,
                        success=llm_response.success,
                        error=llm_response.error,
                        processing_time_ms=processing_time,
                    )

                # Step 1: FETCH - Search vector store (with semantic cache optimization)
                logger.info(
                    "rag_search_started",
                    query=query[:100],
                    collection=collection_name,
                    action=action_taken,
                )

                # [OPTIMIZATION] Check if we can reuse previous context
                if await self._is_semantically_identical(search_query):
                    logger.info("rag_semantic_cache_hit", query=query[:50])
                    contexts = self._last_contexts
                    search_results = []  # Placeholder since we have contexts
                else:
                    from app.services.rag_retrieval_plan import build_retrieval_plan

                    plan = build_retrieval_plan(
                        query=search_query,
                        query_type=None,
                        quality_controls=self.quality_controls,
                        requested_n_results=n_results,
                        requested_score_threshold=score_threshold,
                    )

                    search_results = await self.vector_store.search(
                        query=safe_query,
                        collection_name=collection_name,
                        n_results=plan.top_k,
                        where=effective_filter,
                        score_threshold=plan.score_threshold,
                    )
                    search_results = rank_week_boosted_results(
                        search_results, session_week_index
                    )

                    if not search_results:
                        logger.warning("rag_no_results", query=query[:100])

                        llm_response = await self.llm_service.generate(
                            prompt=query,
                            system_prompt=SYSTEM_RAG_NO_CONTEXT,
                            temperature=TEMPERATURE["rag_no_context"],
                            chat_history=chat_history,
                        )

                        processing_time = (
                            datetime.now() - start_time
                        ).total_seconds() * 1000

                        return RAGResult(
                            answer=llm_response.content,
                            sources=[],
                            query=query,
                            tokens_used=llm_response.tokens_used,
                            success=llm_response.success,
                            error=llm_response.error,
                            processing_time_ms=processing_time,
                        )

                    if plan.use_reranker and self.reranker and self.reranker.enabled:
                        try:
                            reranked_results = await self.reranker.rerank(
                                query=query,
                                documents=search_results,
                                top_k=plan.rerank_top_n,
                            )
                            if reranked_results:
                                search_results = reranked_results
                        except Exception:
                            logger.exception("rag_rerank_fallback")

                    search_results = search_results[
                        : (n_results or self.quality_controls.top_k_results)
                    ]

                    # Step 2: Format contexts & Update semantic cache
                    contexts = self._format_search_results(search_results)
                    self._last_query = query
                    self._last_query_embedding = (
                        None  # PERF-AI-06: Invalidate cached embedding
                    )
                    self._last_contexts = contexts

                # Step 3: Generate response with RAG
                scaffolding_ctx = None
                if guardrail_context and guardrail_context.get("scaffolding_config"):
                    sc = guardrail_context["scaffolding_config"]
                    if sc.get("enabled", True):
                        level = sc.get("scaffolding_level") or "auto"
                        style = ""
                        if level == "early":
                            style = SCAFFOLDING_EARLY_STYLE
                        elif level == "late":
                            style = SCAFFOLDING_LATE_STYLE
                        scaffolding_ctx = (
                            f"Scaffolding level for this cohort: {level}. {style}"
                        )
                llm_response = await self.llm_service.generate_rag_response(
                    query=query,
                    contexts=contexts,
                    chat_history=chat_history,
                    fading_level=fading_level,
                    context=scaffolding_ctx,
                )

                # Step 3.5: Grounding Verification (TA Algorithm 1 OutputGuardrails)
                from app.services.grounding_verifier import get_grounding_verifier

                grounding_verifier = get_grounding_verifier()
                grounding_result = await grounding_verifier.verify_grounding_async(
                    response=llm_response.content,
                    documents=[
                        {"content": c.get("text", c.get("content", ""))}
                        for c in contexts
                    ],
                    threshold=self._grounding_threshold,
                )

                if not grounding_result.is_grounded:
                    logger.warning(
                        "grounding_check_failed",
                        ratio=grounding_result.grounding_ratio,
                        ungrounded=grounding_result.ungrounded_claims[:2],
                    )
                    return RAGResult(
                        answer="Jawaban tidak dapat diberikan tanpa berspekulasi di luar materi yang tersedia.",
                        sources=self._extract_sources(search_results)
                        if search_results
                        else [],
                        query=query,
                        tokens_used=llm_response.tokens_used,
                        success=True,
                        scaffolding_triggered=True,
                        processing_time_ms=(datetime.now() - start_time).total_seconds()
                        * 1000,
                    )

                # Step 4: Output Guardrails (Pedagogy)
                output_check = self.guardrails.check_output(
                    response=llm_response.content,
                    original_query=query,
                    contexts=contexts,
                    context=guardrail_context,
                )
                log_guardrail_decision(
                    output_check, surface="output", route="rag.execute_query"
                )

                scaffolding_triggered = False
                if output_check.action == GuardrailAction.BLOCK:
                    triggered = output_check.triggered_rules or []
                    rule_id = (
                        triggered[0]
                        if triggered
                        else (output_check.reason or "guarded")
                    )
                    return RAGResult(
                        answer=output_check.message
                        or "Maaf, respons dibatasi oleh kebijakan AI course ini.",
                        sources=[],
                        query=query,
                        tokens_used=llm_response.tokens_used,
                        success=True,
                        scaffolding_triggered=True,
                        processing_time_ms=(datetime.now() - start_time).total_seconds()
                        * 1000,
                        outcome="guarded",
                        reason=rule_id,
                    )
                elif output_check.action == GuardrailAction.REDIRECT:
                    # Reframe to Socratic
                    reframed = await self.llm_service.reframe_to_socratic(
                        llm_response.content
                    )
                    llm_response.content = reframed
                    scaffolding_triggered = True
                elif output_check.action == GuardrailAction.SANITIZE:
                    llm_response.content = (
                        output_check.sanitized_input or llm_response.content or ""
                    )

                # Step 5: Extract sources
                sources = self._extract_sources(search_results)
                citations = sources_to_citations(search_results)
                logger.info(
                    "rag_citations_extracted",
                    num_citations=len(citations),
                    has_citations=len(citations) > 0,
                )

                processing_time = (datetime.now() - start_time).total_seconds() * 1000

                logger.info(
                    "rag_query_complete",
                    query=query[:100],
                    num_sources=len(sources),
                    processing_time_ms=processing_time,
                )

                return RAGResult(
                    answer=llm_response.content,
                    sources=sources,
                    query=query,
                    tokens_used=llm_response.tokens_used,
                    success=llm_response.success,
                    scaffolding_triggered=scaffolding_triggered,
                    error=llm_response.error,
                    processing_time_ms=processing_time,
                    citations=citations,
                )

            except Exception:
                processing_time = (datetime.now() - start_time).total_seconds() * 1000

                logger.exception("rag_query_failed", query=query[:100])

                return RAGResult(
                    answer="",
                    sources=[],
                    query=query,
                    tokens_used=0,
                    success=False,
                    error="Internal error",
                    processing_time_ms=processing_time,
                )

        # Use Efficiency Guard if enabled
        if self.efficiency_guard:
            result_dict = await self.efficiency_guard.execute_with_caching(
                query=query,
                query_func=execute_rag_query,
                context=cache_context,
                ttl_seconds=settings.CACHE_TTL_SECONDS,
                use_deduplication=True,
            )

            # Convert dict back to RAGResult if needed
            if isinstance(result_dict, dict):
                return RAGResult(**result_dict)
            return result_dict
        else:
            # Execute without caching
            return await execute_rag_query()

    async def query_stream(
        self,
        query: str,
        collection_name: Optional[str] = None,
        n_results: int = 5,
        chat_history: Optional[List[ChatMessage]] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        fading_level: float = 0.0,
        score_threshold: Optional[float] = None,
        guardrail_context: Optional[Dict[str, Any]] = None,
        session_week_index: Optional[int] = None,
        max_week_index: Optional[int] = None,
        week_context: Optional[Dict[str, Any]] = None,
    ):
        """Async generator for streaming RAG responses.

        PERF-AI-01: Conditional streaming.
        - NO_FETCH path (greetings, short follow-ups): streams tokens directly via
          llm_service.stream_generate(). No grounding/guardrail needed (no retrieved context).
        - FETCH path (substantive questions): delegates to existing query() and yields
          the complete result as a single "full" event. Grounding/guardrails need the
          full response, so streaming is not applicable here.

        Yields dict events:
            {"type": "token", "content": str}   — incremental content (NO_FETCH only)
            {"type": "full", "content": str, "sources": [...], "citations": [...], ...}  — complete result (FETCH)
            {"type": "done", "sources": [...], "citations": [...]}  — terminator
            {"type": "error", "content": str}    — error
        """
        from app.services.week_rag import week_metadata_filter

        week_context_answer = self._answer_from_week_context(query, week_context)
        if week_context_answer is not None:
            yield {
                "type": "full",
                "content": week_context_answer,
                "sources": [],
                "citations": [],
                "outcome": "week_context",
                "reason": "material_list_query",
            }
            yield {"type": "done", "sources": [], "citations": []}
            return

        effective_filter = filter_metadata
        week_cap = week_metadata_filter(max_week_index)
        if week_cap:
            effective_filter = {**(filter_metadata or {}), **week_cap}

        # Input guardrail (same as query())
        guardrail_result = self.guardrails.check_input(query, guardrail_context)
        from app.core.guardrail_diagnostics import log_guardrail_decision

        log_guardrail_decision(
            guardrail_result, surface="input", route="rag.query_stream"
        )

        if guardrail_result.action == GuardrailAction.BLOCK:
            triggered = guardrail_result.triggered_rules or []
            rule_id = (
                triggered[0] if triggered else (guardrail_result.reason or "guarded")
            )
            yield {
                "type": "full",
                "content": guardrail_result.message
                or "Maaf, saya tidak bisa membantu dengan permintaan tersebut.",
                "sources": [],
                "citations": [],
                "outcome": "guarded",
                "reason": rule_id,
            }
            yield {"type": "done", "sources": [], "citations": []}
            return

        safe_query = guardrail_result.sanitized_input or query

        # Query rewriting for short follow-ups
        search_query = safe_query
        if chat_history and len(safe_query.split()) <= 6:
            last_assistant = None
            for msg in reversed(chat_history):
                if msg.role == "assistant":
                    last_assistant = msg.content
                    break
            if last_assistant:
                topic_hint = last_assistant[:200]
                search_query = f"{safe_query} (konteks sebelumnya: {topic_hint})"

        should_fetch = self._should_retrieve(search_query, self._last_contexts)

        if not should_fetch:
            # NO_FETCH: stream tokens directly
            logger.info("rag_stream_no_fetch", query=safe_query[:100])

            no_fetch_prompt = query
            if chat_history:
                history_lines = [
                    f"{'Mahasiswa' if m.role == 'user' else 'Asisten'}: {m.content}"
                    for m in chat_history[-5:]
                ]
                history_text = "\n".join(history_lines)
                no_fetch_prompt = f"Riwayat percakapan:\n{history_text}\n\nPertanyaan terbaru mahasiswa: {query}"

            try:
                async for chunk in self.llm_service.stream_generate(
                    prompt=no_fetch_prompt,
                    system_prompt=SYSTEM_PERSONAL_CHAT,
                    temperature=TEMPERATURE["personal_chat"],
                    chat_history=chat_history,
                ):
                    yield {"type": "token", "content": chunk}
                yield {"type": "done", "sources": [], "citations": []}
            except Exception:
                logger.exception("rag_stream_no_fetch_failed", query=query[:100])
                yield {
                    "type": "error",
                    "content": "Maaf, terjadi kesalahan saat memproses pesan.",
                }
        else:
            # FETCH: delegate to query(), yield full result as single event
            logger.info("rag_stream_fetch_fallback", query=safe_query[:100])
            try:
                result = await self.query(
                    query=query,
                    collection_name=collection_name,
                    n_results=n_results,
                    chat_history=chat_history,
                    filter_metadata=filter_metadata,
                    fading_level=fading_level,
                    score_threshold=score_threshold,
                    guardrail_context=guardrail_context,
                    session_week_index=session_week_index,
                    max_week_index=max_week_index,
                    week_context=week_context,
                )
                yield {
                    "type": "full",
                    "content": result.answer,
                    "sources": result.sources,
                    "citations": result.citations or [],
                    "outcome": result.outcome,
                    "reason": result.reason,
                    "scaffolding_triggered": result.scaffolding_triggered,
                    "grounding_ratio": getattr(result, "grounding_ratio", None),
                }
                yield {
                    "type": "done",
                    "sources": result.sources,
                    "citations": result.citations or [],
                }
            except Exception:
                logger.exception("rag_stream_fetch_failed", query=query[:100])
                yield {
                    "type": "error",
                    "content": "Maaf, terjadi kesalahan saat memproses pesan.",
                }

    async def query_with_course_context(
        self,
        query: str,
        course_id: str,
        chat_room_id: Optional[str] = None,
        n_results: int = 5,
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
            filter_metadata=filter_metadata,
        )

    async def get_similar_questions(
        self, query: str, collection_name: Optional[str] = None, n_results: int = 3
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
                where={"type": "question"},
            )

            similar = []
            for result in results:
                similar.append(
                    {
                        "question": result.get("content", ""),
                        "answer": result.get("metadata", {}).get("answer", ""),
                        "similarity": result.get("score", 0),
                    }
                )

            return similar

        except Exception:
            logger.exception("similar_questions_failed")
            return []

    def _format_search_results(
        self, results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Format search results for LLM context."""
        contexts = []

        for result in results:
            contexts.append(
                {
                    "content": result.get("content", result.get("text", "")),
                    "metadata": result.get("metadata", {}),
                    "score": result.get("score", 0),
                    "rerank_score": result.get("rerank_score"),
                }
            )

        # Preserve reranker ordering when available, otherwise sort by retrieval score.
        contexts.sort(
            key=lambda x: (
                x.get("rerank_score") is not None,
                x.get("rerank_score", x.get("score", 0)),
            ),
            reverse=True,
        )

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

    def _build_rag_token_prompt(
        self, query: str, context_docs: List[Dict[str, Any]]
    ) -> str:
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

    def _extract_sources(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract source information from search results."""
        sources = []
        seen_sources = set()

        for result in results:
            metadata = result.get("metadata", {})
            source = metadata.get("source", "Unknown")

            # Deduplicate sources
            if source not in seen_sources:
                seen_sources.add(source)
                sources.append(
                    {
                        "source": source,
                        "page": metadata.get("page"),
                        "chunk_index": metadata.get("chunk_index"),
                        "relevance_score": result.get("score", 0),
                    }
                )

        return sources


# Singleton instance
_rag_pipeline: Optional[RAGPipeline] = None


def get_rag_pipeline(provider_context: Optional[ProviderContext] = None) -> RAGPipeline:
    """Get or create the RAG pipeline singleton."""
    if provider_context is not None:
        return RAGPipeline(provider_context=provider_context)

    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = RAGPipeline()
    return _rag_pipeline
