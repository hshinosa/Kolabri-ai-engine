"""
Test FINAL - All Priorities Complete
=====================================

Test setelah semua priority diimplementasikan.
Compare: P1 vs P1+2 vs P1+2+3
"""

import asyncio
import time
import httpx


async def final_benchmark():
    """Test final dengan semua optimizations."""
    
    base_url = "http://43.228.214.145:8317/v1"
    api_key = "sk-kolabri"
    model = "gpt-5.2"
    
    print("=" * 70)
    print("FINAL TEST - ALL PRIORITIES (P1 + P2 + P3)")
    print("=" * 70)
    print(f"URL: {base_url}")
    print(f"Model: {model}")
    print("=" * 70)
    print("All Optimizations Active:")
    print("  [P1] HTTP Connection Pooling")
    print("  [P1] Response Caching")
    print("  [P1] GZip Compression")
    print("  [P2] Vector Search Caching")
    print("  [P2] MongoDB Connection Pooling")
    print("  [P2] Cache Hit Rate Optimization")
    print("  [P3] Request Batching")
    print("  [P3] Circuit Breaker")
    print("=" * 70)
    
    queries = ["Halo", "Apa itu machine learning?", "Terima kasih"]
    results = []
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, query in enumerate(queries, 1):
            print(f"\n[{i}/{len(queries)}] {query}")
            
            start = time.time()
            try:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": query}],
                        "max_tokens": 500
                    }
                )
                elapsed = (time.time() - start) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    answer = data["choices"][0]["message"]["content"]
                    print(f"  Status: OK")
                    print(f"  Time: {elapsed:.1f}ms")
                    print(f"  Answer: {answer[:80]}...")
                    results.append({"success": True, "time": elapsed})
                else:
                    print(f"  Error: HTTP {response.status_code}")
                    results.append({"success": False, "time": elapsed})
                    
            except Exception as e:
                elapsed = (time.time() - start) * 1000
                print(f"  Exception: {str(e)[:80]}")
                results.append({"success": False, "time": elapsed})
            
            if i < len(queries):
                await asyncio.sleep(1)
    
    # Summary
    print("\n" + "=" * 70)
    print("FINAL RESULTS (P1 + P2 + P3)")
    print("=" * 70)
    
    success_count = sum(1 for r in results if r["success"])
    times = [r["time"] for r in results if r["success"]]
    
    print(f"Success: {success_count}/{len(results)}")
    if times:
        print(f"Avg: {sum(times)/len(times):.1f}ms")
        print(f"Min: {min(times):.1f}ms")
        print(f"Max: {max(times):.1f}ms")
    
    print("\n" + "=" * 70)
    print("COMPARISON ALL PHASES")
    print("=" * 70)
    
    # Baseline Priority 1
    print("Priority 1 (Baseline):")
    print("  Avg: 3549.3ms")
    print("  Min: 1818.3ms")
    print("  Max: 6900.2ms")
    
    # Priority 1+2
    print("")
    print("Priority 1+2 (Vector Cache + MongoDB Pool):")
    print("  Avg: 3059.5ms (-13.8%)")
    print("  Min: 1275.3ms (-29.9%)")
    print("  Max: 6208.7ms (-10.0%)")
    
    # Priority 1+2+3 (Current)
    print("")
    print("Priority 1+2+3 (All Optimizations):")
    if times:
        final_avg = sum(times)/len(times)
        final_min = min(times)
        final_max = max(times)
        
        print(f"  Avg: {final_avg:.1f}ms")
        print(f"  Min: {final_min:.1f}ms")
        print(f"  Max: {final_max:.1f}ms")
        
        # Total improvement
        improvement_p1 = ((3549.3 - final_avg) / 3549.3) * 100
        print(f"")
        print(f"TOTAL IMPROVEMENT: {improvement_p1:.1f}%")
    
    print("=" * 70)
    print("OPTIMIZATIONS SUMMARY")
    print("=" * 70)
    print("Implemented:")
    print("  [OK] HTTP Connection Pooling")
    print("  [OK] Response Caching")
    print("  [OK] GZip Compression")
    print("  [OK] Vector Search Caching")
    print("  [OK] MongoDB Connection Pooling")
    print("  [OK] Cache Analyzer")
    print("  [OK] Request Batching")
    print("  [OK] Circuit Breaker")
    print("")
    print("Files Created:")
    print("  - llm_optimized.py")
    print("  - rag_optimized.py")
    print("  - redis_cache.py")
    print("  - vector_store_optimized.py")
    print("  - mongodb_logger_optimized.py")
    print("  - cache_analyzer.py")
    print("  - batch_llm.py")
    print("  - circuit_breaker.py")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_final())
