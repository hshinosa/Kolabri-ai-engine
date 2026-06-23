"""
Load Testing Suite for Kolabri AI Engine
==========================================

Menggunakan Locust untuk load testing HTTP endpoint.

Usage:
    # Install dependencies
    pip install -r requirements-loadtest.txt

    # Run load test dengan UI
    locust -f locustfile.py --host=http://localhost:8001

    # Run headless (CLI mode)
    locust -f locustfile.py \
        --host=http://localhost:8001 \
        --users 100 \
        --spawn-rate 10 \
        --run-time 5m \
        --headless \
        --csv=results/ai_engine_load_test

    # Run dengan custom tags
    locust -f locustfile.py --tags=rag --host=http://localhost:8001

Skenario Uji:
    - Health Check: Endpoint sederhana untuk baseline
    - RAG Query (/ask): Simulasi pertanyaan mahasiswa
    - Analytics: Analisis engagement teks
    - Efficiency: Cache dan rate limit stats
    - Group Operations: Status grup dan partisipasi

Output:
    - CSV files dengan metrics
    - HTML report otomatis
    - Statistik response time dan throughput

Author: AI-Engine Team
Issue: KOL-42
"""

import random
import json
from typing import Optional
from locust import HttpUser, task, between, tag, events
from locust.runners import MasterRunner
import requests

from locust_auth import apply_auth_to_client


# =============================================================================
# Configuration
# =============================================================================

# Sample data untuk query RAG
SAMPLE_QUERIES = [
    "Apa itu machine learning?",
    "Jelaskan tentang neural network",
    "Bagaimana cara kerja deep learning?",
    "Apa perbedaan supervised dan unsupervised learning?",
    "Jelaskan konsep overfitting",
    "Apa itu gradient descent?",
    "Bagaimana cara menghindari underfitting?",
    "Jelaskan tentang decision tree",
    "Apa itu random forest?",
    "Bagaimana cara mengevaluasi model ML?",
    "Jelaskan tentang cross-validation",
    "Apa itu precision dan recall?",
    "Bagaimana cara mengatasi imbalanced dataset?",
    "Jelaskan tentang feature engineering",
    "Apa itu hyperparameter tuning?",
    "Bagaimana cara deploy model ML?",
    "Jelaskan tentang transfer learning",
    "Apa itu NLP dan aplikasinya?",
    "Bagaimana cara kerja transformer?",
    "Jelaskan tent attention mechanism",
]

SAMPLE_TEXTS_FOR_ANALYTICS = [
    "Saya sudah mempelajari materi tentang neural network dan memahami cara kerjanya. "
    "Konsep backpropagation sangat menarik karena memungkinkan model belajar dari error. "
    "Bagaimana cara mengoptimalkan learning rate agar training lebih efisien?",
    "Menurut saya, implementasi decision tree lebih mudah dipahami dibanding neural network. "
    "Namun, saya bingung kapan harus menggunakan random forest. "
    "Apakah ada guideline untuk memilih algoritma yang tepat?",
    "Saya telah mencoba membuat model klasifikasi menggunakan Scikit-learn. "
    "Hasilnya cukup bagus dengan accuracy 85%. "
    "Tapi saya ingin meningkatkan performa model. Apa yang bisa dilakukan?",
    "Diskusi kita tentang feature selection sangat membantu. "
    "Saya menyadari bahwa tidak semua feature perlu digunakan. "
    "Bagaimana cara menentukan feature yang paling penting?",
    "Saya tertarik untuk mengeksplorasi deep learning untuk image classification. "
    "CNN sepertinya cocok untuk tugas ini. "
    "Apakah ada tutorial atau contoh implementasi yang bisa saya pelajari?",
]

# Config untuk load test
LOAD_TEST_CONFIG = {
    "health_check_weight": 10,  # 10% traffic
    "rag_query_weight": 50,  # 50% traffic - endpoint utama
    "analytics_weight": 20,  # 20% traffic
    "efficiency_weight": 10,  # 10% traffic
    "group_ops_weight": 10,  # 10% traffic
}


# =============================================================================
# Event Handlers
# =============================================================================


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts."""
    print("\n" + "=" * 70)
    print("🚀 AI ENGINE LOAD TEST STARTED")
    print("=" * 70)
    print(f"Target Host: {environment.host}")
    print(f"Test Scenarios: Health, RAG Query, Analytics, Efficiency, Group Ops")
    print("=" * 70 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops."""
    print("\n" + "=" * 70)
    print("✅ AI ENGINE LOAD TEST COMPLETED")
    print("=" * 70)
    print("Generate report with: python generate_report.py")
    print("=" * 70 + "\n")


@events.request.add_listener
def on_request(
    request_type,
    name,
    response_time,
    response_length,
    response,
    context,
    exception,
    **kwargs,
):
    """Track custom metrics if needed."""
    pass


# =============================================================================
# User Classes
# =============================================================================


class AIEngineUser(HttpUser):
    """
    Simulated user yang mengakses AI Engine API.

    User behavior:
    - Wait 1-5 detik antara request (simulasi thinking time)
    - Pilih endpoint berdasarkan weight configuration
    - Kirim data realistis (query akademik, teks analisis, dll)
    """

    wait_time = between(1, 5)  # Think time 1-5 detik

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.course_id = f"course_{random.randint(1, 10)}"
        self.user_id = f"user_{random.randint(1000, 9999)}"
        self.group_id = f"group_{random.randint(1, 50)}"
        self.session_discussion_id = f"space_{random.randint(1, 200)}"

    def on_start(self):
        """Called when user starts."""
        apply_auth_to_client(self.client)
        self.client.get("/api/health", name="/api/health (warmup)")

    # ========================================================================
    # Health Check (10% traffic)
    # ========================================================================

    @tag("health")
    @task(LOAD_TEST_CONFIG["health_check_weight"])
    def health_check(self):
        """Test health check endpoint - baseline performance."""
        with self.client.get(
            "/api/health", name="/api/health", catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("status") in ["healthy", "degraded"]:
                        response.success()
                    else:
                        response.failure(f"Unexpected status: {data.get('status')}")
                except Exception as e:
                    response.failure(f"Invalid JSON: {e}")
            else:
                response.failure(f"HTTP {response.status_code}")

    # ========================================================================
    # RAG Query (50% traffic) - Endpoint Kritis
    # ========================================================================

    @tag("rag")
    @task(LOAD_TEST_CONFIG["rag_query_weight"])
    def ask_question(self):
        """Test /ask endpoint - simulasi pertanyaan mahasiswa."""
        query = random.choice(SAMPLE_QUERIES)

        payload = {
            "query": query,
            "course_id": self.course_id,
            "user_name": f"Student {self.user_id}",
            "session_discussion_id": self.session_discussion_id,
        }

        with self.client.post(
            "/api/ask",
            json=payload,
            name="/ask (RAG Query)",
            catch_response=True,
            timeout=60,  # RAG bisa lambat
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("success"):
                        response.success()
                    else:
                        # Masih sukses HTTP, tapi AI tidak berhasil jawab
                        response.success()
                except Exception as e:
                    response.failure(f"Invalid JSON: {e}")
            elif response.status_code == 0:
                response.failure("Connection error/timeout")
            else:
                response.failure(f"HTTP {response.status_code}")

    @tag("rag")
    @task(5)
    def ask_question_with_long_query(self):
        """Test /ask dengan query panjang (edge case)."""
        long_query = (
            "Saya ingin memahami bagaimana cara kerja neural network dalam machine learning. "
            "Apakah bisa dijelaskan langkah demi langkah mulai dari input layer, hidden layer, "
            "sampai output layer? Bagaimana proses forward propagation dan backpropagation? "
            "Apa perbedaan antara activation function ReLU, Sigmoid, dan Tanh? "
            "Kapan kita harus menggunakan masing-masing?"
        )

        payload = {
            "query": long_query,
            "course_id": self.course_id,
            "user_name": f"Student {self.user_id}",
            "session_discussion_id": self.session_discussion_id,
        }

        with self.client.post(
            "/api/ask",
            json=payload,
            name="/ask (Long Query)",
            catch_response=True,
            timeout=60,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 0:
                response.failure("Connection error/timeout")
            else:
                response.failure(f"HTTP {response.status_code}")

    # ========================================================================
    # Analytics (20% traffic)
    # ========================================================================

    @tag("analytics")
    @task(LOAD_TEST_CONFIG["analytics_weight"])
    def analyze_engagement(self):
        """Test /analytics/engagement endpoint."""
        text = random.choice(SAMPLE_TEXTS_FOR_ANALYTICS)

        payload = {"text": text}

        with self.client.post(
            "/api/analytics/engagement",
            json=payload,
            name="/api/analytics/engagement",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("success"):
                        response.success()
                    else:
                        response.success()  # Still valid response
                except Exception as e:
                    response.failure(f"Invalid JSON: {e}")
            elif response.status_code == 0:
                response.failure("Connection error/timeout")
            else:
                response.failure(f"HTTP {response.status_code}")

    @tag("analytics")
    @task(5)
    def get_group_dashboard(self):
        """Test group dashboard endpoint."""
        with self.client.get(
            f"/api/analytics/dashboard/group/{self.group_id}",
            name="/api/analytics/dashboard/group/{id}",
            catch_response=True,
        ) as response:
            if response.status_code in [200, 404]:  # 404 ok jika group tidak ada
                response.success()
            elif response.status_code == 0:
                response.failure("Connection error/timeout")
            else:
                response.failure(f"HTTP {response.status_code}")

    @tag("analytics")
    @task(3)
    def get_individual_dashboard(self):
        """Test individual dashboard endpoint."""
        with self.client.get(
            f"/api/analytics/dashboard/individual/{self.user_id}",
            name="/api/analytics/dashboard/individual/{id}",
            catch_response=True,
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            elif response.status_code == 0:
                response.failure("Connection error/timeout")
            else:
                response.failure(f"HTTP {response.status_code}")

    # ========================================================================
    # Efficiency/Cache (10% traffic)
    # ========================================================================

    @tag("efficiency")
    @task(LOAD_TEST_CONFIG["efficiency_weight"])
    def get_cache_statistics(self):
        """Test cache statistics endpoint."""
        with self.client.get(
            "/api/efficiency/cache/statistics",
            name="/api/efficiency/cache/statistics",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 0:
                response.failure("Connection error/timeout")
            else:
                response.failure(f"HTTP {response.status_code}")

    @tag("efficiency")
    @task(3)
    def get_efficiency_statistics(self):
        """Test comprehensive efficiency statistics."""
        with self.client.get(
            "/api/efficiency/statistics",
            name="/api/efficiency/statistics",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 0:
                response.failure("Connection error/timeout")
            else:
                response.failure(f"HTTP {response.status_code}")

    @tag("efficiency")
    @task(2)
    def get_high_frequency_queries(self):
        """Test high frequency queries endpoint."""
        with self.client.get(
            "/api/efficiency/high-frequency-queries?limit=10",
            name="/api/efficiency/high-frequency-queries",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 0:
                response.failure("Connection error/timeout")
            else:
                response.failure(f"HTTP {response.status_code}")

    # ========================================================================
    # Group Operations (10% traffic)
    # ========================================================================

    @tag("group")
    @task(LOAD_TEST_CONFIG["group_ops_weight"])
    def check_group_status(self):
        """Test group status check endpoint."""
        with self.client.get(
            f"/api/groups/{self.group_id}/status",
            name="/api/groups/{id}/status",
            catch_response=True,
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            elif response.status_code == 0:
                response.failure("Connection error/timeout")
            else:
                response.failure(f"HTTP {response.status_code}")

    @tag("group")
    @task(3)
    def track_participation(self):
        """Test participation tracking endpoint."""
        payload = {"user_id": self.user_id}

        with self.client.post(
            f"/api/groups/{self.group_id}/track-participation",
            data=payload,
            name="/api/groups/{id}/track-participation",
            catch_response=True,
        ) as response:
            if response.status_code in [200, 404]:
                response.success()
            elif response.status_code == 0:
                response.failure("Connection error/timeout")
            else:
                response.failure(f"HTTP {response.status_code}")


class SpikeTestUser(HttpUser):
    """
    User class untuk spike testing - burst traffic.

    Simulasi: Banyak user login bersamaan di awal sesi.
    """

    wait_time = between(0.1, 0.5)  # Minimal think time

    def on_start(self):
        apply_auth_to_client(self.client)

    @task
    def spike_health_check(self):
        """Rapid health checks during spike."""
        self.client.get("/api/health", name="/health (spike)")


class SteadyStateUser(HttpUser):
    """
    User class untuk steady-state testing.

    Simulasi: Traffic normal yang stabil sepanjang waktu.
    """

    wait_time = between(3, 8)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.course_id = f"course_{random.randint(1, 10)}"
        self.user_id = f"user_{random.randint(1000, 9999)}"
        self.session_discussion_id = f"space_{random.randint(1, 200)}"

    def on_start(self):
        apply_auth_to_client(self.client)

    @task(10)
    def steady_health_check(self):
        """Regular health checks."""
        self.client.get("/api/health", name="/health (steady)")

    @task(50)
    def steady_ask_question(self):
        """Regular RAG queries."""
        query = random.choice(SAMPLE_QUERIES)
        payload = {
            "query": query,
            "course_id": self.course_id,
            "user_name": f"Student {self.user_id}",
            "session_discussion_id": self.session_discussion_id,
        }
        self.client.post("/api/ask", json=payload, name="/ask (steady)", timeout=60)

    @task(20)
    def steady_analytics(self):
        """Regular analytics calls."""
        text = random.choice(SAMPLE_TEXTS_FOR_ANALYTICS)
        self.client.post(
            "/api/analytics/engagement",
            json={"text": text},
            name="/api/analytics/engagement (steady)",
        )

    @task(20)
    def steady_efficiency(self):
        """Regular efficiency checks."""
        self.client.get(
            "/api/efficiency/statistics", name="/api/efficiency/statistics (steady)"
        )
