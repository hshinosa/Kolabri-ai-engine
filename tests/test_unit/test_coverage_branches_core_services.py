"""Branch coverage for app/core + app/services (coverage-remaining-gaps.md §2)."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.modules.setdefault("chromadb", MagicMock())
sys.modules.setdefault("motor", MagicMock())
sys.modules.setdefault("motor.motor_asyncio", MagicMock())
sys.modules.setdefault("redis.asyncio", MagicMock())
sys.modules.setdefault("redis", MagicMock())


@pytest.mark.asyncio
async def test_get_cache_analyzer_singleton_initializes_once():
    import app.core.cache_analyzer as ca

    ca._cache_analyzer = None
    with patch.object(ca.CacheAnalyzer, "initialize", new_callable=AsyncMock) as init_mock:
        first = await ca.get_cache_analyzer()
        second = await ca.get_cache_analyzer()
    assert first is second
    init_mock.assert_awaited_once()
    ca._cache_analyzer = None


@pytest.mark.asyncio
async def test_core_circuit_breaker_record_success_resets_failures_when_closed():
    from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState

    cb = CircuitBreaker("t", CircuitBreakerConfig(failure_threshold=5, success_threshold=2))
    cb.state = CircuitState.CLOSED
    cb.failure_count = 3
    await cb._record_success()
    assert cb.failure_count == 0


def test_config_production_docs_warning_both_doc_flags():
    with patch("app.core.config.logger.warning") as mock_warning:
        from app.core.config import Settings

        Settings(
            ENV="production",
            OPENAI_API_KEY="sk-prod-key-1234567890",
            OPENAI_BASE_URL="https://api.openai.com/v1",
            CORE_API_URL="https://api.example.com",
            CORE_API_SECRET="x" * 40,
            DEBUG=False,
            DOCS_ENABLED=True,
            ENABLE_DOCS_IN_PRODUCTION=False,
        )
    assert mock_warning.call_count >= 2


def test_guardrails_toxicity_warn_empty_triggered_rules_skips_extend():
    from app.core.guardrails import GuardrailAction, GuardrailResult, Guardrails

    g = Guardrails()
    tox = GuardrailResult(action=GuardrailAction.WARN, reason="toxicity", triggered_rules=[])
    allow = GuardrailResult(action=GuardrailAction.ALLOW, reason="ok")
    with (
        patch.object(g, "_check_prompt_injection", return_value=allow),
        patch.object(g, "_check_harmful_content", return_value=allow),
        patch.object(g, "_check_academic_dishonesty", return_value=allow),
        patch.object(g, "_check_off_topic", return_value=allow),
        patch.object(g, "_check_pii", return_value=allow),
        patch.object(g, "_check_toxicity", return_value=tox),
    ):
        out = g.check_input("jelaskan konsep dasar")
    assert out.action == GuardrailAction.ALLOW
    assert out.reason == "all_checks_passed"
    assert out.triggered_rules == []


@pytest.mark.asyncio
async def test_service_circuit_breaker_success_in_closed_resets_failure_count():
    from app.services.circuit_breaker import CircuitBreaker, CircuitState

    cb = CircuitBreaker(name="svc", failure_threshold=3, success_threshold=2)
    cb._state = CircuitState.CLOSED
    cb._failure_count = 2
    await cb._on_success()
    assert cb._failure_count == 0


@pytest.mark.asyncio
async def test_service_circuit_breaker_failure_in_closed_below_threshold():
    from app.services.circuit_breaker import CircuitBreaker, CircuitState

    cb = CircuitBreaker(name="svc", failure_threshold=5, success_threshold=2)
    cb._state = CircuitState.CLOSED
    await cb._on_failure()
    assert cb._state == CircuitState.CLOSED
    assert cb._failure_count == 1


def test_service_circuit_breaker_should_attempt_reset_when_no_last_failure():
    from app.services.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker(name="svc")
    cb._last_failure_time = None
    assert cb._should_attempt_reset() is True


@pytest.mark.asyncio
async def test_service_circuit_breaker_call_skips_error_log_for_circuit_breaker_error():
    from app.services.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError, CircuitState

    cb = CircuitBreaker(name="svc", failure_threshold=5, success_threshold=2)
    cb._state = CircuitState.CLOSED

    async def fail():
        raise CircuitBreakerOpenError("already open")

    with patch("app.services.circuit_breaker.logger.error") as log_err:
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(fail)
    log_err.assert_not_called()


@pytest.mark.asyncio
async def test_query_deduplicator_finally_when_key_already_removed():
    from app.services.efficiency_guard import QueryDeduplicator

    dedup = QueryDeduplicator()
    real_lock = dedup.query_lock

    class LockProxy:
        async def __aenter__(self):
            await real_lock.__aenter__()
            dedup.pending_queries.pop("q1", None)
            return self

        async def __aexit__(self, *args):
            return await real_lock.__aexit__(*args)

    async def ok():
        return {"ok": True}

    with patch.object(dedup, "query_lock", LockProxy()):
        out = await dedup.execute_or_wait("q1", ok)
    assert out == {"ok": True}


@pytest.mark.asyncio
async def test_efficiency_guard_del_expired_when_cleanup_noop():
    from app.services.efficiency_guard import CacheEntry, EfficiencyGuard

    guard = EfficiencyGuard(max_cache_size=10, cache_ttl_seconds=3600)
    key = guard._generate_cache_key("q", None)
    guard.cache[key] = CacheEntry({"v": 1}, ttl_seconds=-1)
    with patch.object(guard, "_cleanup_expired_cache", new=AsyncMock()):
        assert await guard.get_cached_response("q", None) is None
    assert key not in guard.cache


def test_reranker_import_error_sets_cross_encoder_unavailable():
    import app.services.reranker as mod

    saved = sys.modules.get("fastembed.rerank.cross_encoder")
    sys.modules["fastembed.rerank.cross_encoder"] = None
    try:
        reloaded = importlib.reload(mod)
        assert reloaded.CROSS_ENCODER_AVAILABLE is False
    finally:
        if saved is not None:
            sys.modules["fastembed.rerank.cross_encoder"] = saved
        else:
            sys.modules.pop("fastembed.rerank.cross_encoder", None)
        importlib.reload(mod)


def test_rag_quality_evaluate_suite_partial_match_wrong_top_hit():
    from app.services.rag_quality import (
        RetrievalEvaluationCase,
        RetrievalQualityEvaluator,
        RetrievalQualityReviewCriteria,
    )

    ev = RetrievalQualityEvaluator(RetrievalQualityReviewCriteria(min_cases=1))
    summary = ev.evaluate_suite(
        [
            RetrievalEvaluationCase(
                query="q",
                expected_sources=["doc-a"],
                retrieved_sources=["doc-b", "doc-a"],
                fallback_used=False,
            ),
        ]
    )
    assert summary.passed_cases == 1
    assert summary.top_hit_rate == 0.0
    assert summary.average_source_recall > 0


@pytest.mark.asyncio
async def test_rag_benchmark_runner_duplicate_benchmark_role_branch():
    from app.services.rag_benchmark_bootstrap import NormalizedBenchmarkCase
    from app.services.rag_benchmark_runner import BenchmarkExecutionResult, RAGBenchmarkRunner

    case = NormalizedBenchmarkCase(
        case_id="c1",
        source_dataset="ds",
        benchmark_role="role_a",
        query="q",
        expected_answer="a",
        contexts=[],
        expected_sources=[],
        metadata={},
    )

    async def exec_case(_c):
        return BenchmarkExecutionResult(
            case_id="c1",
            source_dataset="ds",
            benchmark_role="role_a",
            retrieved_sources=[],
            generated_answer="",
            fallback_used=False,
            metrics={"score": 1.0},
        )

    with patch.object(Path, "mkdir"), patch.object(Path, "write_text"):
        report = await RAGBenchmarkRunner(Path("/tmp/bench")).run(
            [case, case], exec_case, report_name="t"
        )
    assert report.datasets["ds"]["benchmark_roles"] == ["role_a"]


@pytest.mark.asyncio
async def test_mongo_log_activity_skips_when_disabled():
    from app.services.mongodb_logger import MongoDBLogger

    logger = MongoDBLogger()
    logger.enabled = False
    logger.db = MagicMock()
    await logger.log_activity({"CaseID": "c1", "Activity": "A"})
    logger.db.activity_logs.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_mongo_log_activity_insert_failure_logged():
    from app.services.mongodb_logger import MongoDBLogger

    logger = MongoDBLogger()
    logger.enabled = True
    logger.db = MagicMock()
    logger.db.activity_logs.insert_one = AsyncMock(side_effect=RuntimeError("db"))
    with patch("app.services.mongodb_logger.logger.error") as log_err:
        await logger.log_activity({"CaseID": "c1", "Activity": "A", "Attributes": {}})
    log_err.assert_called_once()


@pytest.mark.asyncio
async def test_vector_store_delete_documents_with_where_filter():
    from app.services.vector_store import VectorStoreService

    svc = VectorStoreService()
    svc._initialized = True
    svc._client = MagicMock()
    with patch.object(svc, "_ensure_collection", new_callable=AsyncMock):
        await svc.delete_documents(collection_name="c1", where={"course_id": "x"})
    svc._client.delete.assert_called_once()


@pytest.mark.asyncio
async def test_vector_store_search_filters_low_score_points():
    from app.services.vector_store import VectorStoreService

    svc = VectorStoreService()
    svc._initialized = True
    svc._client = MagicMock()
    svc._embedding_service = MagicMock()
    svc._embedding_service.embed_query = AsyncMock(return_value=[0.1])
    low = MagicMock(score=0.01, payload={"content": "low"})
    high = MagicMock(score=0.99, payload={"content": "high"})
    svc._client.query_points.return_value = SimpleNamespace(points=[low, high])
    with patch.object(svc, "_ensure_collection", new_callable=AsyncMock):
        with patch("app.services.vector_store.settings") as st:
            st.SIMILARITY_THRESHOLD = 0.5
            out = await svc.search("q", collection_name="c1", n_results=5)
    assert len(out) == 1
    assert out[0]["content"] == "high"


def test_chunking_short_text_single_chunk():
    from app.services.document_processing.chunking import create_chunks

    chunks = create_chunks("Hello world.", "doc1", "f.txt", 1, 500, 50)
    assert len(chunks) == 1


def test_chunking_long_text_while_loop_and_overlap():
    from app.services.document_processing.chunking import create_chunks

    para = "Word " * 200
    text = para + "\n\n" + para
    chunks = create_chunks(text, "doc1", "f.txt", 1, 400, 50)
    assert len(chunks) >= 2
    assert all(c.metadata.get("chunk_count") == len(chunks) for c in chunks)


def test_xes_exporter_bool_and_numeric_event_attributes():
    import xml.etree.ElementTree as ET

    from app.services.xes_exporter import XESExporter

    exp = XESExporter()
    ev = ET.Element("event")
    exp._add_event_attributes(
        ev,
        {
            "activity": "A",
            "timestamp": "2026-01-01T00:00:00",
            "resource": "u",
            "attributes": {"flag": True, "score": 1.5, "note": "x"},
        },
    )
    assert ev.find("boolean[@key='flag']") is not None
    assert ev.find("float[@key='score']") is not None


@pytest.mark.asyncio
async def test_export_aggregate_by_group_computes_engagement_score():
    from app.services.export_service import ExportService

    svc = ExportService()
    with patch.object(svc, "initialize", new_callable=AsyncMock):
        with patch("app.services.repositories.ActivityLogRepository") as Repo:
            Repo.return_value.list_student_messages_for_group = AsyncMock(
                return_value=[
                    {
                        "Resource": "u1",
                        "Attributes": {
                            "original_text": "hello world",
                            "is_hot": True,
                            "lexical_variety": 0.5,
                        },
                    },
                ]
            )
            rows = await svc.aggregate_activity_by_group("g1")
    assert rows[0]["engagement_score"] > 0


@pytest.mark.asyncio
async def test_export_aggregate_by_chat_space_sorts_by_message_count():
    from app.services.export_service import ExportService

    svc = ExportService()
    with patch.object(svc, "initialize", new_callable=AsyncMock):
        with patch("app.services.repositories.ActivityLogRepository") as Repo:
            Repo.return_value.list_student_messages_for_case = AsyncMock(
                return_value=[
                    {"Resource": "u1", "Attributes": {"original_text": "a"}},
                    {"Resource": "u2", "Attributes": {"original_text": "b"}},
                    {"Resource": "u2", "Attributes": {"original_text": "c"}},
                ]
            )
            rows = await svc.aggregate_activity_by_chat_space("space-1")
    assert rows[0]["user_id"] == "u2"


@pytest.mark.asyncio
async def test_intervention_check_triggers_needs_summary_branch():
    from app.services.intervention import ChatInterventionService

    svc = ChatInterventionService(llm_service=MagicMock())
    svc.minimum_messages_for_summary = 5
    now = datetime.now(timezone.utc)
    messages = [
        {"timestamp": (now - timedelta(minutes=i)).isoformat(), "content": f"m{i}"}
        for i in range(10, 0, -1)
    ]
    triggers = await svc._check_triggers(
        messages=messages,
        topic="algoritma",
        last_intervention_time=now - timedelta(hours=3),
    )
    assert triggers["needs_summary"] is True


def test_process_mining_anomaly_bottleneck_skips_empty_duration_list():
    from app.services.process_mining_anomaly import ProcessMiningAnomalyDetector

    det = ProcessMiningAnomalyDetector()
    assert det._detect_bottlenecks([]) is None


@pytest.mark.asyncio
async def test_orchestrator_handle_message_rag_failure_reply():
    from app.services.nlp_analytics import EngagementAnalysis, EngagementType
    from app.services.orchestration import Orchestrator

    orch = Orchestrator.__new__(Orchestrator)
    orch.analyzer = MagicMock()
    orch.analyzer.analyze_interaction.return_value = EngagementAnalysis(
        lexical_variety=0.7,
        engagement_type=EngagementType.COGNITIVE,
        is_higher_order=True,
        hot_indicators=[],
        word_count=5,
        unique_words=5,
        confidence=0.8,
    )
    orch.analyzer.extract_srl_object = MagicMock(return_value="obj")
    rag_result = SimpleNamespace(
        success=False,
        answer="ignored",
        sources=[],
        scaffolding_triggered=False,
        outcome="ok",
        reason=None,
    )
    orch.rag = MagicMock()
    orch.rag.query = AsyncMock(return_value=rag_result)
    orch.mongo_logger = MagicMock()
    orch.mongo_logger.log_activity = AsyncMock()
    orch.logic_listener = MagicMock()
    orch.logic_listener.track_participation = AsyncMock()
    orch.logic_listener.update_last_message_time = AsyncMock()
    orch.anomaly_detector = MagicMock()
    orch.anomaly_detector.detect_session_anomalies = AsyncMock(
        return_value=SimpleNamespace(has_anomalies=False)
    )
    orch.notification_service = MagicMock()
    orch._state_lock = __import__("asyncio").Lock()
    orch._group_messages = {}
    orch._group_fading_levels = {}
    orch._last_intervention = {}
    with patch("app.services.orchestration.settings") as st:
        st.INTERVENTION_MIN_MESSAGES = 99
        result = await orch.handle_message("u1", "g1", "hi", topic="t")
    assert "Maaf" in result.reply


@pytest.mark.asyncio
async def test_orchestrator_should_intervene_cooldown_returns_false():
    from app.services.nlp_analytics import EngagementAnalysis, EngagementType
    from app.services.orchestration import Orchestrator

    orch = Orchestrator.__new__(Orchestrator)
    orch._state_lock = __import__("asyncio").Lock()
    orch._last_intervention = {"g1": datetime.now()}
    orch.logic_listener = MagicMock()
    orch.logic_listener.get_group_status.return_value = {"participation_gini": 0.0}
    analytics = EngagementAnalysis(
        lexical_variety=0.1,
        engagement_type=EngagementType.COGNITIVE,
        is_higher_order=False,
        hot_indicators=[],
        word_count=1,
        unique_words=1,
        confidence=0.5,
    )
    with patch("app.services.orchestration.settings") as st:
        st.INTERVENTION_COOLDOWN_MINUTES = 60
        st.NLP_LOW_LEXICAL_THRESHOLD = 0.0
        st.NLP_QUALITY_ALERT_THRESHOLD = 0.0
        st.LOGIC_LISTENER_PARTICIPATION_INEQUITY_THRESHOLD = 1.0
        needed, reason = await orch._should_intervene("g1", analytics, 10.0)
    assert needed is False
    assert reason is None