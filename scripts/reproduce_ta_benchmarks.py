#!/usr/bin/env python3
"""
Reproduce TA Bab 4 performance evidence from a live AI Engine.

Outputs: data/evaluation/performance/reproduction_YYYYMMDD_HHMMSS.json

Usage:
  cd Kolabri-ai-engine && source .venv/bin/activate
  python scripts/reproduce_ta_benchmarks.py --host http://127.0.0.1:8001
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import uuid
from datetime import datetime, UTC
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_bearer() -> str:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    secret = os.getenv("CORE_API_SECRET", "")
    if not secret:
        raise SystemExit("CORE_API_SECRET missing in .env")
    return secret


SAMPLE_TEXT = (
    "Saya sudah mempelajari materi tentang neural network dan memahami cara kerjanya. "
    "Bagaimana cara mengoptimalkan learning rate?"
)


async def timed_request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
) -> tuple[float, int]:
    start = time.perf_counter()
    if method == "GET":
        r = await client.get(path)
    else:
        r = await client.post(path, json=json_body)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return elapsed_ms, r.status_code


async def bench_endpoint(
    client: httpx.AsyncClient,
    name: str,
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    n: int = 30,
    concurrency: int = 5,
) -> dict:
    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    statuses: list[int] = []

    async def one() -> None:
        async with sem:
            ms, code = await timed_request(client, method, path, json_body=json_body)
            latencies.append(ms)
            statuses.append(code)

    wall_start = time.perf_counter()
    await asyncio.gather(*[one() for _ in range(n)])
    wall_s = time.perf_counter() - wall_start

    ok = sum(1 for c in statuses if c == 200)
    mean_ms = statistics.mean(latencies) if latencies else 0
    p95 = sorted(latencies)[int(0.95 * len(latencies)) - 1] if latencies else 0
    rps = n / wall_s if wall_s > 0 else 0

    return {
        "name": name,
        "method": method,
        "path": path,
        "samples": n,
        "concurrency": concurrency,
        "success_200": ok,
        "wall_seconds": round(wall_s, 3),
        "rps": round(rps, 2),
        "latency_ms": {
            "mean": round(mean_ms, 2),
            "min": round(min(latencies), 2) if latencies else 0,
            "max": round(max(latencies), 2) if latencies else 0,
            "p95": round(p95, 2),
        },
        "status_codes": dict(
            sorted({c: statuses.count(c) for c in set(statuses)}.items())
        ),
    }


async def rag_cold_vs_cached(client: httpx.AsyncClient, course_id: str) -> dict:
    """First call = cold-ish; repeat same query = semantic/response cache."""
    query = "Jelaskan gradient descent untuk optimasi model"
    body = {
        "query": query,
        "course_id": course_id,
        "user_name": "bench_repro",
    }
    cold_ms, cold_code = await timed_request(client, "POST", "/api/ask", json_body=body)
    cached_samples: list[float] = []
    for _ in range(5):
        ms, code = await timed_request(client, "POST", "/api/ask", json_body=body)
        if code == 200:
            cached_samples.append(ms)
        await asyncio.sleep(0.2)

    cached_mean = statistics.mean(cached_samples) if cached_samples else 0
    speedup = (cold_ms / cached_mean) if cached_mean > 0 else None

    return {
        "endpoint": "/api/ask",
        "cold_first_ms": round(cold_ms, 2),
        "cold_http": cold_code,
        "cached_repeat_mean_ms": round(cached_mean, 2),
        "cached_samples": len(cached_samples),
        "speedup_x": round(speedup, 2) if speedup else None,
        "note": "Repeat identical query; cache hit depends on Redis/semantic cache config.",
    }


async def main_async(host: str, engagement_n: int, health_n: int) -> Path:
    host = host.rstrip("/")
    bearer = load_bearer()
    headers = {"Authorization": f"Bearer {bearer}"}
    out_dir = ROOT / "data" / "evaluation" / "performance"
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"reproduction_{stamp}.json"

    limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
    async with httpx.AsyncClient(
        base_url=host, headers=headers, timeout=120.0, limits=limits
    ) as client:
        health_probe_ms, health_code = await timed_request(client, "GET", "/api/health")
        if health_code not in (200, 503):
            raise SystemExit(f"/api/health unexpected HTTP {health_code}")

        course_id = f"bench_{uuid.uuid4().hex[:8]}"
        sections: dict = {
            "meta": {
                "generated_at": datetime.now(UTC).isoformat(),
                "host": host,
                "engine": "kolabri-ai-engine",
                "purpose": "Bab4 TA performance reproduction",
                "health_probe_ms": round(health_probe_ms, 2),
                "health_http": health_code,
            },
            "engagement_analysis": await bench_endpoint(
                client,
                "Engagement Analysis",
                "POST",
                "/api/analytics/engagement",
                json_body={"text": SAMPLE_TEXT},
                n=engagement_n,
                concurrency=10,
            ),
            "health_check": await bench_endpoint(
                client,
                "Health",
                "GET",
                "/api/health",
                n=health_n,
                concurrency=10,
            ),
            "rag_cold_cached": await rag_cold_vs_cached(client, course_id),
        }

        # Unique-query RAG (mostly cold per request)
        unique_latencies: list[float] = []
        for i in range(3):
            body = {
                "query": f"Pertanyaan unik benchmark {uuid.uuid4().hex} tentang ML",
                "course_id": course_id,
                "user_name": "bench",
            }
            ms, code = await timed_request(client, "POST", "/api/ask", json_body=body)
            if code == 200:
                unique_latencies.append(ms)

        sections["rag_unique_queries"] = {
            "samples": len(unique_latencies),
            "latency_ms_mean": round(statistics.mean(unique_latencies), 2)
            if unique_latencies
            else None,
            "note": "Each query unique — approximates cold RAG latency (includes LLM).",
        }

    payload = sections
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="http://127.0.0.1:8001")
    parser.add_argument("--engagement-n", type=int, default=50)
    parser.add_argument("--health-n", type=int, default=50)
    args = parser.parse_args()
    out = asyncio.run(main_async(args.host, args.engagement_n, args.health_n))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
