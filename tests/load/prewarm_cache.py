"""
Pre-warm Cache untuk Uji Stres
==============================

Script untuk mempopulate cache dengan responses sebelum menjalankan uji stres.
Ini penting untuk mencapai target <100ms P95 latency dengan 2500 RPS.

Usage:
    python prewarm_cache.py --queries queries.txt --course-id c1

Issue: KOL-42 - High Performance Targets
"""

import asyncio
import argparse
import os
import time
from pathlib import Path
from typing import List

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


DEFAULT_QUERIES = [
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


async def prewarm_single_query(
    client: httpx.AsyncClient, host: str, query: str, course_id: str
) -> bool:
    """Prewarm cache untuk single query."""
    try:
        response = await client.post(
            f"{host.rstrip('/')}/api/ask",
            json={
                "query": query,
                "course_id": course_id,
                "user_name": "prewarm",
            },
            timeout=30.0,
        )

        if response.status_code == 200:
            print(f"  ✅ Cached: {query[:50]}...")
            return True
        else:
            print(f"  ❌ Failed: {query[:50]}... (HTTP {response.status_code})")
            return False

    except Exception as e:
        print(f"  ❌ Error: {query[:50]}... ({str(e)})")
        return False


async def prewarm_cache(
    queries: List[str], host: str, course_id: str, concurrent: int = 5
):
    """Prewarm cache dengan multiple queries."""

    print(f"\n{'=' * 60}")
    print("🔥 PRE-WARMING CACHE")
    print(f"{'=' * 60}")
    print(f"Host: {host}")
    print(f"Queries: {len(queries)}")
    print(f"Concurrent: {concurrent}")
    print(f"{'=' * 60}\n")

    # Create client dengan connection pooling
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    secret = os.getenv("CORE_API_SECRET", "").strip()
    headers = {"Authorization": f"Bearer {secret}"} if secret else {}
    async with httpx.AsyncClient(
        limits=limits, timeout=30.0, headers=headers
    ) as client:
        # Test health check dulu
        try:
            response = await client.get(f"{host.rstrip('/')}/api/health")
            if response.status_code in (200, 503):
                print("✅ AI Engine is reachable\n")
            else:
                print(f"⚠️ AI Engine health check returned {response.status_code}\n")
        except Exception as e:
            print(f"❌ Cannot connect to AI Engine: {e}\n")
            return

        # Prewarm dengan semaphore untuk limit concurrency
        semaphore = asyncio.Semaphore(concurrent)

        async def prewarm_with_limit(query: str) -> bool:
            async with semaphore:
                return await prewarm_single_query(client, host, query, course_id)

        start_time = time.time()

        # Execute all
        results = await asyncio.gather(
            *[prewarm_with_limit(query) for query in queries]
        )

        elapsed = time.time() - start_time

        success_count = sum(results)
        failed_count = len(results) - success_count

        print(f"\n{'=' * 60}")
        print("📊 PRE-WARM COMPLETED")
        print(f"{'=' * 60}")
        print(f"Total: {len(queries)}")
        print(f"Success: {success_count}")
        print(f"Failed: {failed_count}")
        print(f"Time: {elapsed:.1f}s")
        print(f"Avg: {elapsed / len(queries):.2f}s per query")
        print(f"{'=' * 60}\n")


def load_queries_from_file(filepath: str) -> List[str]:
    """Load queries dari file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"❌ File not found: {filepath}")
        return []


def main():
    parser = argparse.ArgumentParser(description="Pre-warm cache untuk uji stres")
    parser.add_argument("--queries", help="File containing queries (one per line)")
    parser.add_argument(
        "--host", default="http://localhost:8001", help="AI Engine host"
    )
    parser.add_argument("--course-id", default="c1", help="Course ID untuk queries")
    parser.add_argument(
        "--concurrent", type=int, default=5, help="Concurrent requests (default: 5)"
    )

    args = parser.parse_args()

    # Load queries
    if args.queries:
        queries = load_queries_from_file(args.queries)
        if not queries:
            print("Using default queries...")
            queries = DEFAULT_QUERIES
    else:
        queries = DEFAULT_QUERIES

    # Run prewarm
    asyncio.run(prewarm_cache(queries, args.host, args.course_id, args.concurrent))

    print("\n✅ Cache pre-warmed! Ready for stress test.")
    print(f"\nRun stress test:")
    print(f"  python run_high_perf_test.py --scenario uji_stres --host {args.host}")


if __name__ == "__main__":
    main()
