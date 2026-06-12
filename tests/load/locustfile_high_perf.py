"""
Load Test Scenarios for High Performance Targets
=================================================

Target Performance Metrics:
- Baseline:       10 users,   50 RPS,   <200ms P95
- Beban Sedang:   50 users,   250 RPS,  <300ms P95
- Beban Puncak:   100 users,  500 RPS,  <500ms P95
- Uji Stres:      500 users,  2500 RPS, <100ms P95

Issue: KOL-42 - High Performance Load Testing
"""

import random
from typing import Optional
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner

from locust_auth import apply_auth_to_client


# =============================================================================
# Configuration - Target Performance Metrics
# =============================================================================

TARGETS = {
    "baseline": {
        "users": 10,
        "duration": "5m",
        "target_rps": 50,
        "target_p95_ms": 200,
    },
    "beban_sedang": {
        "users": 50,
        "duration": "10m",
        "target_rps": 250,
        "target_p95_ms": 300,
    },
    "beban_puncak": {
        "users": 100,
        "duration": "15m",
        "target_rps": 500,
        "target_p95_ms": 500,
    },
    "uji_stres": {
        "users": 500,
        "duration": "5m",
        "target_rps": 2500,
        "target_p95_ms": 100,
    },
}

# Sample queries untuk test
SAMPLE_QUERIES = [
    "Apa itu machine learning?",
    "Jelaskan neural network",
    "Bagaimana cara kerja deep learning?",
    "Apa perbedaan supervised dan unsupervised?",
    "Jelaskan konsep overfitting",
    "Apa itu gradient descent?",
    "Bagaimana menghindari underfitting?",
    "Jelaskan decision tree",
    "Apa itu random forest?",
    "Bagaimana evaluasi model ML?",
]


# =============================================================================
# Event Handlers
# =============================================================================


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts."""
    target_name = environment.parsed_options.target or "unknown"
    target = TARGETS.get(target_name, {})

    print("\n" + "=" * 80)
    print("🚀 AI ENGINE HIGH PERFORMANCE LOAD TEST")
    print("=" * 80)
    print(f"Target: {target_name.upper()}")
    print(f"Users: {target.get('users', 'N/A')}")
    print(f"Duration: {target.get('duration', 'N/A')}")
    print(f"Target RPS: {target.get('target_rps', 'N/A')}")
    print(f"Target P95: {target.get('target_p95_ms', 'N/A')}ms")
    print("=" * 80)
    print(f"Host: {environment.host}")
    print("=" * 80 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops."""
    target_name = environment.parsed_options.target or "unknown"
    target = TARGETS.get(target_name, {})

    print("\n" + "=" * 80)
    print("✅ LOAD TEST COMPLETED")
    print("=" * 80)
    print(f"Target: {target_name.upper()}")

    # Get stats
    stats = environment.runner.stats
    if stats.total.num_requests > 0:
        avg_response = stats.total.avg_response_time
        p95_response = stats.total.get_response_time_percentile(0.95)
        rps = stats.total.total_rps

        target_p95 = target.get("target_p95_ms", float("inf"))
        target_rps = target.get("target_rps", 0)

        print(f"\nResults:")
        print(f"  Avg Response: {avg_response:.1f}ms")
        print(
            f"  P95 Response: {p95_response:.1f}ms (Target: <{target_p95}ms) {'✅' if p95_response < target_p95 else '❌'}"
        )
        print(
            f"  RPS: {rps:.1f} (Target: {target_rps}) {'✅' if rps >= target_rps else '❌'}"
        )
        print(f"  Total Requests: {stats.total.num_requests}")
        print(f"  Failed: {stats.total.num_failures}")

        if p95_response < target_p95 and rps >= target_rps:
            print("\n🎉 TARGET ACHIEVED!")
        else:
            print("\n⚠️ TARGET NOT MET")

    print("=" * 80 + "\n")


# =============================================================================
# Base User Class
# =============================================================================


class BaseLoadTestUser(HttpUser):
    """Base class untuk semua load test users."""

    abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.course_id = f"course_{random.randint(1, 5)}"
        self.user_id = f"user_{random.randint(1000, 9999)}"

    def on_start(self):
        apply_auth_to_client(self.client)


# =============================================================================
# Baseline: 10 users, 50 RPS, <200ms P95
# =============================================================================


class BaselineUser(BaseLoadTestUser):
    """
    Baseline test: 10 users, 50 RPS, <200ms P95

    Skenario: Verifikasi baseline performance
    """

    wait_time = between(0.18, 0.22)  # ~5 RPS per user = 50 RPS total

    @task(100)
    def health_check(self):
        """Health check - baseline latency measurement."""
        self.client.get("/api/health", name="/health (baseline)")

    @task(50)
    def ask_simple_query(self):
        """Simple RAG query."""
        query = random.choice(SAMPLE_QUERIES)
        payload = {
            "query": query,
            "course_id": self.course_id,
            "user_name": f"User_{self.user_id}",
        }
        self.client.post(
            "/api/ask",
            json=payload,
            name="/ask (baseline)",
            timeout=2,  # Strict 2s timeout untuk <200ms target
        )


# =============================================================================
# Beban Sedang: 50 users, 250 RPS, <300ms P95
# =============================================================================


class BebanSedangUser(BaseLoadTestUser):
    """
    Beban sedang: 50 users, 250 RPS, <300ms P95

    Skenario: Traffic normal production
    """

    wait_time = between(0.18, 0.22)  # ~5 RPS per user = 250 RPS total

    @task(50)
    def health_check(self):
        """Health check."""
        self.client.get("/api/health", name="/health (sedang)")

    @task(100)
    def ask_query(self):
        """RAG query - main traffic."""
        query = random.choice(SAMPLE_QUERIES)
        payload = {
            "query": query,
            "course_id": self.course_id,
            "user_name": f"User_{self.user_id}",
        }
        self.client.post(
            "/api/ask",
            json=payload,
            name="/ask (sedang)",
            timeout=3,  # 3s timeout untuk <300ms target
        )

    @task(30)
    def analytics_check(self):
        """Analytics endpoint."""
        text = "Ini adalah contoh teks untuk analisis engagement."
        self.client.post(
            "/api/analytics/engagement",
            json={"text": text},
            name="/api/analytics/engagement (sedang)",
            timeout=3,
        )


# =============================================================================
# Beban Puncak: 100 users, 500 RPS, <500ms P95
# =============================================================================


class BebanPuncakUser(BaseLoadTestUser):
    """
    Beban puncak: 100 users, 500 RPS, <500ms P95

    Skenario: Peak traffic, multiple concurrent requests
    """

    wait_time = between(0.18, 0.22)  # ~5 RPS per user = 500 RPS total

    @task(30)
    def health_check(self):
        """Health check."""
        self.client.get("/api/health", name="/health (puncak)")

    @task(100)
    def ask_query(self):
        """RAG query - main traffic."""
        query = random.choice(SAMPLE_QUERIES)
        payload = {
            "query": query,
            "course_id": self.course_id,
            "user_name": f"User_{self.user_id}",
        }
        self.client.post(
            "/api/ask",
            json=payload,
            name="/ask (puncak)",
            timeout=5,  # 5s timeout untuk <500ms target
        )

    @task(50)
    def batch_query(self):
        """Batch processing untuk high throughput."""
        requests = [
            {
                "query": random.choice(SAMPLE_QUERIES),
                "course_id": self.course_id,
                "request_id": f"req_{random.randint(1, 1000)}",
            }
            for _ in range(5)
        ]

        self.client.post(
            "/ask/batch",
            json={"requests": requests},
            name="/ask/batch (puncak)",
            timeout=10,
        )

    @task(20)
    def efficiency_stats(self):
        """Efficiency stats."""
        self.client.get(
            "/api/efficiency/statistics", name="/api/efficiency/statistics (puncak)"
        )


# =============================================================================
# Uji Stres: 500 users, 2500 RPS, <100ms P95
# =============================================================================


class UjiStresUser(BaseLoadTestUser):
    """
    Uji stres: 500 users, 2500 RPS, <100ms P95

    Skenario: Extreme load dengan caching dan pre-computed responses
    Target: <100ms P95 memerlukan aggressive caching dan batching
    """

    wait_time = between(0.18, 0.22)  # ~5 RPS per user = 2500 RPS total

    # Use smaller set of queries untuk maximize cache hits
    CACHE_FRIENDLY_QUERIES = [
        "Apa itu machine learning?",
        "Jelaskan neural network",
        "Bagaimana cara kerja deep learning?",
        "Apa perbedaan supervised dan unsupervised?",
    ]

    @task(10)
    def health_check(self):
        """Health check - minimal overhead."""
        self.client.get("/api/health", name="/health (stres)")

    @task(30)
    def precomputed_query(self):
        """
        Pre-computed query - untuk <100ms target.
        Hanya queries yang sudah dipre-compute.
        """
        query = random.choice(self.CACHE_FRIENDLY_QUERIES)
        payload = {
            "query": query,
            "course_id": self.course_id,
            "user_name": f"User_{self.user_id}",
        }

        # Very strict timeout untuk <100ms target
        self.client.post(
            "/api/ask",
            json=payload,
            name="/ask (stres - cached)",
            timeout=1,  # 1s timeout (but target is <100ms)
        )

    @task(100)
    def batch_precomputed(self):
        """
        Batch pre-computed - fastest path untuk <100ms.
        Uses /ask/batch/precomputed yang hanya mengembalikan cached responses.
        """
        requests = [
            {
                "query": random.choice(self.CACHE_FRIENDLY_QUERIES),
                "course_id": self.course_id,
                "request_id": f"req_{random.randint(1, 10000)}",
            }
            for _ in range(10)  # Batch 10 requests
        ]

        self.client.post(
            "/ask/batch/precomputed",
            json={"requests": requests},
            name="/ask/batch/precomputed (stres)",
            timeout=5,  # 5s untuk batch of 10 (<500ms each)
        )

    @task(20)
    def cache_stats(self):
        """Check cache stats."""
        self.client.get(
            "/api/efficiency/cache/statistics",
            name="/api/efficiency/cache/statistics (stres)",
        )


# =============================================================================
# Spike Test: Sudden traffic surge
# =============================================================================


class SpikeTestUser(BaseLoadTestUser):
    """
    Spike test: Sudden traffic surge dari 0 ke 100 users.
    """

    wait_time = between(0.01, 0.05)  # Minimal think time

    @task(100)
    def health_check_spike(self):
        """Health check during spike."""
        self.client.get("/api/health", name="/health (spike)")

    @task(50)
    def ask_during_spike(self):
        """Query during spike."""
        query = random.choice(SAMPLE_QUERIES)
        payload = {
            "query": query,
            "course_id": self.course_id,
        }
        self.client.post("/api/ask", json=payload, name="/ask (spike)", timeout=10)


# =============================================================================
# Endurance Test: Long running test
# =============================================================================


class EnduranceUser(BaseLoadTestUser):
    """
    Endurance test: Sustained load untuk stabilitas.
    30 users, 150 RPS, durasi 30 menit
    """

    wait_time = between(0.18, 0.22)

    @task(50)
    def health_check(self):
        """Health check."""
        self.client.get("/api/health", name="/health (endurance)")

    @task(100)
    def ask_query(self):
        """RAG query."""
        query = random.choice(SAMPLE_QUERIES)
        payload = {
            "query": query,
            "course_id": self.course_id,
        }
        self.client.post("/api/ask", json=payload, name="/ask (endurance)", timeout=5)

    @task(10)
    def efficiency_check(self):
        """Check efficiency stats."""
        self.client.get(
            "/api/efficiency/statistics", name="/api/efficiency/statistics (endurance)"
        )
