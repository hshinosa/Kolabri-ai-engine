"""Bearer auth for Locust against /api routes (CORE_API_SECRET from .env)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def bearer_headers() -> dict[str, str]:
    secret = os.getenv("CORE_API_SECRET", "").strip()
    if not secret:
        return {}
    return {"Authorization": f"Bearer {secret}"}


def apply_auth_to_client(client) -> None:
    headers = bearer_headers()
    if headers:
        client.headers.update(headers)
