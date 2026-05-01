from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import monitoring
from app.services.monitoring import (
    LLMCallTracker,
    PerformanceMonitor,
    RAGQueryTracker,
    RequestTracker,
    get_monitor,
)


def test_track_request_returns_request_tracker():
    monitor = PerformanceMonitor()

    tracker = monitor.track_request("POST", "/api/test")

    assert isinstance(tracker, RequestTracker)
    assert tracker.method == "POST"
    assert tracker.endpoint == "/api/test"


def test_track_llm_call_returns_llm_tracker():
    monitor = PerformanceMonitor()

    tracker = monitor.track_llm_call("gpt-test")

    assert isinstance(tracker, LLMCallTracker)
    assert tracker.model == "gpt-test"


def test_track_rag_query_returns_rag_tracker():
    monitor = PerformanceMonitor()

    tracker = monitor.track_rag_query("FETCH")

    assert isinstance(tracker, RAGQueryTracker)
    assert tracker.action == "FETCH"


def test_record_cache_hit_increments_counter():
    monitor = PerformanceMonitor()
    labels_obj = MagicMock()

    with patch.object(monitoring.CACHE_HIT_COUNT, "labels", return_value=labels_obj) as labels:
        monitor.record_cache_hit("response_cache")

    labels.assert_called_once_with(cache_type="response_cache")
    labels_obj.inc.assert_called_once_with()


def test_record_cache_miss_increments_counter():
    monitor = PerformanceMonitor()
    labels_obj = MagicMock()

    with patch.object(monitoring.CACHE_MISS_COUNT, "labels", return_value=labels_obj) as labels:
        monitor.record_cache_miss("embedding_cache")

    labels.assert_called_once_with(cache_type="embedding_cache")
    labels_obj.inc.assert_called_once_with()


def test_record_rag_query_increments_counter():
    monitor = PerformanceMonitor()
    labels_obj = MagicMock()

    with patch.object(monitoring.RAG_QUERY_COUNT, "labels", return_value=labels_obj) as labels:
        monitor.record_rag_query("courses", "FETCH")

    labels.assert_called_once_with(collection="courses", action="FETCH")
    labels_obj.inc.assert_called_once_with()


def test_record_error_increments_counter():
    monitor = PerformanceMonitor()
    labels_obj = MagicMock()

    with patch.object(monitoring.ERROR_COUNT, "labels", return_value=labels_obj) as labels:
        monitor.record_error("timeout", "/api/rag")

    labels.assert_called_once_with(type="timeout", endpoint="/api/rag")
    labels_obj.inc.assert_called_once_with()


def test_update_circuit_breaker_state_sets_gauge():
    monitor = PerformanceMonitor()
    labels_obj = MagicMock()

    with patch.object(monitoring.CIRCUIT_BREAKER_STATE, "labels", return_value=labels_obj) as labels:
        monitor.update_circuit_breaker_state("llm_service", 2)

    labels.assert_called_once_with(service="llm_service")
    labels_obj.set.assert_called_once_with(2)


def test_update_active_connections_sets_gauge():
    monitor = PerformanceMonitor()

    with patch.object(monitoring.ACTIVE_CONNECTIONS, "set") as set_mock:
        monitor.update_active_connections(7)

    set_mock.assert_called_once_with(7)


def test_get_metrics_returns_generated_payload():
    monitor = PerformanceMonitor()

    with patch("app.services.monitoring.generate_latest", return_value=b"metric 1") as generate:
        payload = monitor.get_metrics()

    generate.assert_called_once_with()
    assert payload == b"metric 1"


def test_get_content_type_returns_prometheus_content_type():
    monitor = PerformanceMonitor()

    assert monitor.get_content_type() == monitoring.CONTENT_TYPE_LATEST


def test_get_dashboard_data_returns_uptime_and_endpoint():
    monitor = PerformanceMonitor()
    monitor.start_time = datetime.now() - timedelta(seconds=3661)

    with patch.object(monitor, "_format_uptime", return_value="1h 1m") as formatter:
        data = monitor.get_dashboard_data()

    assert data["metrics_available"] is True
    assert data["metrics_endpoint"] == "/metrics"
    formatter.assert_called_once()
    assert data["uptime_seconds"] >= 3660
    assert data["uptime_human"] == "1h 1m"


def test_format_uptime_handles_days_hours_minutes():
    monitor = PerformanceMonitor()

    assert monitor._format_uptime(90061) == "1d 1h 1m"


def test_format_uptime_handles_less_than_one_minute():
    monitor = PerformanceMonitor()

    assert monitor._format_uptime(59) == "< 1m"


def test_request_tracker_records_success_metrics():
    labels_count = MagicMock()
    labels_latency = MagicMock()

    with patch.object(monitoring.REQUEST_COUNT, "labels", return_value=labels_count) as count_labels, patch.object(
        monitoring.REQUEST_LATENCY,
        "labels",
        return_value=labels_latency,
    ) as latency_labels, patch("app.services.monitoring.time.time", side_effect=[10.0, 10.75]):
        with RequestTracker("GET", "/api/demo"):
            pass

    count_labels.assert_called_once_with(method="GET", endpoint="/api/demo", status="success")
    labels_count.inc.assert_called_once_with()
    latency_labels.assert_called_once_with(method="GET", endpoint="/api/demo")
    labels_latency.observe.assert_called_once_with(0.75)


def test_request_tracker_records_error_status_when_exception_occurs():
    labels_count = MagicMock()
    labels_latency = MagicMock()
    tracker = RequestTracker("POST", "/api/fail")

    with patch.object(monitoring.REQUEST_COUNT, "labels", return_value=labels_count), patch.object(
        monitoring.REQUEST_LATENCY,
        "labels",
        return_value=labels_latency,
    ), patch("app.services.monitoring.time.time", side_effect=[20.0, 20.2]):
        tracker.__enter__()
        tracker.__exit__(RuntimeError, RuntimeError("boom"), None)

    labels_count.inc.assert_called_once_with()
    labels_latency.observe.assert_called_once_with(0.1999999999999993)


def test_llm_call_tracker_records_success_and_latency():
    labels_count = MagicMock()
    labels_latency = MagicMock()

    with patch.object(monitoring.LLM_CALL_COUNT, "labels", return_value=labels_count) as count_labels, patch.object(
        monitoring.LLM_CALL_LATENCY,
        "labels",
        return_value=labels_latency,
    ) as latency_labels, patch("app.services.monitoring.time.time", side_effect=[30.0, 31.5]):
        with LLMCallTracker("gpt-4"):
            pass

    count_labels.assert_called_once_with(model="gpt-4", status="success")
    labels_count.inc.assert_called_once_with()
    latency_labels.assert_called_once_with(model="gpt-4")
    labels_latency.observe.assert_called_once_with(1.5)


def test_rag_query_tracker_records_latency_only():
    labels_latency = MagicMock()

    with patch.object(monitoring.RAG_QUERY_LATENCY, "labels", return_value=labels_latency) as latency_labels, patch(
        "app.services.monitoring.time.time",
        side_effect=[100.0, 100.4],
    ):
        with RAGQueryTracker("NO_FETCH"):
            pass

    latency_labels.assert_called_once_with(action="NO_FETCH")
    labels_latency.observe.assert_called_once_with(0.4000000000000057)


def test_get_monitor_returns_singleton_instance():
    monitoring._monitor = None

    first = get_monitor()
    second = get_monitor()

    assert first is second
    assert isinstance(first, PerformanceMonitor)
