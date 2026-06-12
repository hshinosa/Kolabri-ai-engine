"""Minimal Locust repro for TA — uses /api/* + Bearer auth from CORE_API_SECRET."""

import os
import random
from pathlib import Path

from dotenv import load_dotenv
from locust import HttpUser, task, between

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
_SECRET = os.getenv("CORE_API_SECRET", "")


class ReproUser(HttpUser):
    wait_time = between(0.1, 0.3)

    def on_start(self):
        if _SECRET:
            self.client.headers.update({"Authorization": f"Bearer {_SECRET}"})

    @task(3)
    def engagement(self):
        self.client.post(
            "/api/analytics/engagement",
            json={
                "text": "Saya memahami neural network dan ingin diskusi learning rate."
            },
            name="/api/analytics/engagement",
        )

    @task(1)
    def health(self):
        self.client.get("/api/health", name="/api/health")
