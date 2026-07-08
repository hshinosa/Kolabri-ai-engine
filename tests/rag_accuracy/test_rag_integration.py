"""
RAG Integration Faithfulness Test
==================================

Mengukur faithfulness RAG system sebenarnya dengan:
1. Hit /api/ask endpoint dengan query
2. Ambil LLM response dan retrieved contexts
3. Evaluate faithfulness score
"""

import asyncio
import httpx
from typing import List, Dict, Any
from datetime import datetime
import uuid
from tests.rag_accuracy.test_faithfulness import FaithfulnessEvaluator

BASE_URL = "http://localhost:8001"
AUTH_TOKEN = "shared-secret-key"
CORE_API_URL = "http://core-api:3000"

INTEGRATION_TEST_QUERIES = [
    {
        "name": "React SPA Architecture",
        "query": "Jelaskan konsep Single Page Application dalam React",
        "course_id": "IF201",
        "expected_keywords": ["SPA", "React", "routing"],
    },
    {
        "name": "REST API Integration",
        "query": "Bagaimana cara mengintegrasikan REST API dalam aplikasi web?",
        "course_id": "IF201",
        "expected_keywords": ["REST", "API", "fetch", "axios"],
    },
    {
        "name": "Machine Learning Basics",
        "query": "Apa itu K-Means clustering?",
        "course_id": "IF211",
        "expected_keywords": ["K-Means", "clustering", "centroid"],
    },
]


async def fetch_provider_context() -> Dict[str, Any]:
    """Fetch provider context from Core API."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{CORE_API_URL}/api/internal/ai-provider/active",
            headers={"X-Internal-Secret": AUTH_TOKEN},
        )
        response.raise_for_status()
        data = response.json()
        provider = data["data"]

        return {
            "version": "1.0",
            "provider": {
                "name": provider["name"],
                "displayName": provider["displayName"],
            },
            "execution": {
                "baseUrl": provider["baseUrl"],
                "model": provider["config"]["defaultModel"],
                "temperature": provider["config"]["temperature"],
                "maxTokens": provider["config"]["maxTokens"],
            },
            "auth": {
                "type": "api-key",
                "credential": provider["apiKey"],
            },
            "metadata": {
                "featureFamily": "rag",
                "requestId": str(uuid.uuid4()),
                "resolvedAt": datetime.utcnow().isoformat() + "Z",
            },
        }


async def call_rag_endpoint(
    query: str, course_id: str, provider_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Call /api/ask endpoint dan return response."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{BASE_URL}/api/ask",
            headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
            json={
                "query": query,
                "course_id": course_id,
                "user_name": "Test User",
                "provider_context": provider_context,
            },
        )

        if response.status_code == 422:
            print(f"    Validation Error Details: {response.json()}")

        response.raise_for_status()
        return response.json()


async def main():
    """Run RAG integration faithfulness tests."""
    print("=" * 70)
    print("RAG INTEGRATION FAITHFULNESS TEST")
    print("=" * 70)
    print(f"Target Score: > 0.85")
    print("=" * 70)
    print()

    print("Fetching provider context from Core API...")
    try:
        provider_context = await fetch_provider_context()
        print(f"Provider: {provider_context['execution']['model']}")
        print()
    except Exception as e:
        print(f"ERROR: Failed to fetch provider context: {e}")
        return

    evaluator = FaithfulnessEvaluator()
    total_score = 0.0
    passed_tests = 0

    for test_case in INTEGRATION_TEST_QUERIES:
        print(f"Test: {test_case['name']}")
        print(f"  Query: {test_case['query']}")
        print(f"  Course ID: {test_case['course_id']}")

        try:
            rag_response = await call_rag_endpoint(
                test_case["query"], test_case["course_id"], provider_context
            )

            print(f"  Raw Response: {rag_response}")
            print()

            answer = rag_response.get("answer", "")
            contexts_raw = rag_response.get("contexts", [])

            contexts = [
                ctx.get("content", "") for ctx in contexts_raw if ctx.get("content")
            ]

            print(f"  Retrieved Contexts: {len(contexts)}")
            print(f"  Answer Length: {len(answer)} chars")

            result = await evaluator.evaluate(answer, contexts)

            print(f"  Total Claims: {result.total_claims}")
            print(f"  Supported: {result.supported_claims}")
            print(f"  Unsupported: {result.unsupported_claims}")
            print(f"  Faithfulness Score: {result.score:.3f}")
            print(f"  Status: {'[PASS]' if evaluator.passed(result) else '[FAIL]'}")

            if evaluator.passed(result):
                passed_tests += 1

            total_score += result.score

            if result.unsupported_claims > 0:
                print(f"  Unsupported Claims:")
                for detail in result.details:
                    if not detail["supported"]:
                        print(f"    - {detail['claim'][:100]}...")

        except Exception as e:
            print(f"  ERROR: {str(e)}")
            print(f"  Status: [ERROR]")

        print()

    avg_score = total_score / len(INTEGRATION_TEST_QUERIES)
    print("=" * 70)
    print(f"SUMMARY:")
    print(f"  Tests Passed: {passed_tests}/{len(INTEGRATION_TEST_QUERIES)}")
    print(f"  Average Faithfulness Score: {avg_score:.3f}")
    print(f"  Overall Status: {'[PASS]' if avg_score >= 0.85 else '[FAIL]'}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
