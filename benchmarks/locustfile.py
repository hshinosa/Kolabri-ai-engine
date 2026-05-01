"""
Kolabri AI Engine - Load Testing Suite
======================================
Run: locust -f benchmarks/locustfile.py --host=http://localhost:8001
Web UI: http://localhost:8089

Targets:
- Health check: <10ms P95
- RAG query: <500ms P95
- Personal chat: <1000ms P95
- Batch (10 items): <2000ms P95
- Analytics: <200ms P95
"""

import json
import random
import string
from locust import HttpUser, task, between, tag


def random_text(length=50):
    words = [
        "machine learning", "deep learning", "neural network", "algoritma",
        "data science", "artificial intelligence", "natural language",
        "computer vision", "reinforcement learning", "supervised learning",
        "unsupervised learning", "transfer learning", "model training",
        "gradient descent", "backpropagation", "convolutional", "recurrent",
        "transformer", "attention mechanism", "embedding", "tokenization",
        "fine-tuning", "pre-training", "inference", "optimization",
    ]
    return " ".join(random.choices(words, k=length // 2))


SAMPLE_QUERIES = [
    "Apa itu machine learning?",
    "Jelaskan perbedaan supervised dan unsupervised learning",
    "Bagaimana cara kerja neural network?",
    "Apa itu gradient descent?",
    "Jelaskan konsep backpropagation",
    "Apa perbedaan CNN dan RNN?",
    "Bagaimana transformer bekerja?",
    "Apa itu attention mechanism?",
    "Jelaskan transfer learning",
    "Apa itu reinforcement learning?",
    "Bagaimana cara fine-tuning model?",
    "Apa itu embedding dalam NLP?",
    "Jelaskan tokenization",
    "Apa itu overfitting dan underfitting?",
    "Bagaimana cara mengatasi vanishing gradient?",
]

COURSE_IDS = ["course_ml_101", "course_ai_201", "course_ds_301"]
GROUP_IDS = ["group_a1", "group_b2", "group_c3"]
USER_IDS = ["user_001", "user_002", "user_003", "user_004", "user_005"]


class HealthCheckUser(HttpUser):
    """Lightweight user that only hits health endpoints."""
    weight = 3
    wait_time = between(0.5, 1)

    @tag("health")
    @task(5)
    def health_check(self):
        self.client.get("/api/health")

    @tag("health")
    @task(1)
    def circuit_breaker_status(self):
        self.client.get("/api/health/circuit-breakers")

    @tag("health")
    @task(1)
    def reranker_status(self):
        self.client.get("/api/health/reranker")


class RAGQueryUser(HttpUser):
    """User that performs RAG queries (main workload)."""
    weight = 5
    wait_time = between(1, 3)

    @tag("rag")
    @task(10)
    def ask_question(self):
        query = random.choice(SAMPLE_QUERIES)
        course_id = random.choice(COURSE_IDS)
        self.client.post("/api/ask", json={
            "query": query,
            "course_id": course_id,
            "user_name": random.choice(USER_IDS),
        })

    @tag("rag", "batch")
    @task(2)
    def batch_ask(self):
        requests = [
            {
                "query": random.choice(SAMPLE_QUERIES),
                "course_id": random.choice(COURSE_IDS),
                "request_id": f"req_{i}",
            }
            for i in range(random.randint(3, 10))
        ]
        self.client.post("/api/batch/ask/batch", json={
            "requests": requests,
            "priority": "normal",
        })

    @tag("rag")
    @task(1)
    def ask_with_long_query(self):
        self.client.post("/api/ask", json={
            "query": random_text(100),
            "course_id": random.choice(COURSE_IDS),
        })


class PersonalChatUser(HttpUser):
    """User that uses personal AI chat."""
    weight = 3
    wait_time = between(2, 5)

    @tag("chat")
    @task(5)
    def personal_chat(self):
        self.client.post("/api/chat/personal", json={
            "message": random.choice(SAMPLE_QUERIES),
            "user_id": random.choice(USER_IDS),
            "course_id": random.choice(COURSE_IDS),
        })

    @tag("chat", "orchestration")
    @task(3)
    def orchestrated_chat(self):
        self.client.post("/api/chat", json={
            "user_id": random.choice(USER_IDS),
            "group_id": random.choice(GROUP_IDS),
            "message": random.choice(SAMPLE_QUERIES),
            "topic": "Machine Learning Basics",
            "course_id": random.choice(COURSE_IDS),
        })


class AnalyticsUser(HttpUser):
    """User that queries analytics endpoints."""
    weight = 2
    wait_time = between(3, 8)

    @tag("analytics")
    @task(3)
    def engagement_analysis(self):
        self.client.post("/api/analytics/engagement", json={
            "text": random_text(30),
        })

    @tag("analytics")
    @task(2)
    def group_dashboard(self):
        group_id = random.choice(GROUP_IDS)
        self.client.get(f"/api/analytics/dashboard/group/{group_id}")

    @tag("analytics")
    @task(2)
    def individual_dashboard(self):
        user_id = random.choice(USER_IDS)
        self.client.get(f"/api/analytics/dashboard/individual/{user_id}")

    @tag("analytics")
    @task(1)
    def group_analytics_alias(self):
        group_id = random.choice(GROUP_IDS)
        self.client.get(f"/api/analytics/group/{group_id}")

    @tag("analytics")
    @task(1)
    def cache_stats(self):
        self.client.get("/api/efficiency/cache-stats")

    @tag("analytics")
    @task(1)
    def rate_limit_stats(self):
        self.client.get("/api/efficiency/rate-limit-stats")


class InterventionUser(HttpUser):
    """User that triggers intervention analysis."""
    weight = 1
    wait_time = between(5, 15)

    @tag("intervention")
    @task(3)
    def analyze_intervention(self):
        messages = [
            {"role": "user", "content": msg}
            for msg in random.sample(SAMPLE_QUERIES, min(5, len(SAMPLE_QUERIES)))
        ]
        self.client.post("/api/intervention/analyze", json={
            "messages": messages,
            "topic": "AI Ethics",
            "chat_room_id": "room_1",
        })

    @tag("intervention")
    @task(2)
    def generate_summary(self):
        messages = [
            {"role": "user", "content": msg}
            for msg in random.sample(SAMPLE_QUERIES, min(8, len(SAMPLE_QUERIES)))
        ]
        self.client.post("/api/intervention/summary", json={
            "messages": messages,
            "chat_room_id": "room_1",
        })

    @tag("intervention")
    @task(1)
    def generate_prompt(self):
        self.client.post("/api/intervention/prompt", json={
            "topic": "Deep Learning",
            "context": "Students are discussing CNN architectures",
            "difficulty": "intermediate",
        })


class GoalValidationUser(HttpUser):
    """User that validates learning goals."""
    weight = 1
    wait_time = between(5, 10)

    @tag("goals")
    @task(3)
    def validate_goal(self):
        goals = [
            "Saya ingin belajar machine learning dalam 2 minggu",
            "Membuat 3 project deep learning sebelum akhir semester",
            "Memahami konsep NLP",
            "Menyelesaikan 10 latihan coding Python minggu ini",
        ]
        self.client.post("/api/goals/validate", json={
            "goal_text": random.choice(goals),
        })

    @tag("goals")
    @task(1)
    def refine_goal(self):
        self.client.post("/api/goals/refine", json={
            "goal_text": "Saya ingin belajar",
            "missing_criteria": ["measurable", "time_bound"],
        })
