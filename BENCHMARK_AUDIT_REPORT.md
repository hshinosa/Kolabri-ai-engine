# Performance Benchmark Audit Report
## Kolabri AI Engine - Bab 4 TA Claims Verification

> **Catatan (Juni 2026):** Laporan ini adalah **audit awal pra-reproduksi** terhadap klaim lama di naskah. Naskah TA dan Bab 4 telah diselaraskan dengan bukti di `docs/evidence/bab4/` (`REPRODUCTION_REPORT.md`, JSON rerank, Locust/HTTP repro). Verdict di bawah **tidak** menggambarkan status naskah final; baca laporan reproduksi untuk angka yang dipakai sidang.

**Audit Date:** 2026-06-12
**Auditor:** Sisyphus-Junior
**Scope:** `/Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/`

---

## Executive Summary

**ALL 8 CLAIMS ARE UNVERIFIED** *(snapshot codebase sebelum repro TA; lihat catatan di atas).* None of the specific benchmark numbers claimed in Bab 4 exist in the codebase. The benchmark infrastructure (Locust tests, pytest-benchmark) exists but shows no evidence of ever being executed. The numbers appear to be **estimates/fabrications** rather than actual measurements.

---

## Claim-by-Claim Verification

### Claim 1: "RAG Query cold: 2.236 ms, cached: 286 ms, speedup 7.8x"

**VERDICT: MISMATCH - NO EVIDENCE**

**Evidence:**
- Searched entire codebase for values `2.236`, `286`, `7.8x`, `7.8` - **ZERO matches**
- `tests/load/locustfile.py` tests `/ask` endpoint but records no baseline latency numbers
- `app/services/rag.py` tracks `processing_time_ms` but no cold vs cached comparison exists
- `app/core/cache_analyzer.py` tracks hit rate but not latency differential
- `tests/load/results/` directory is empty (only `.gitkeep`)

**Assessment:** These precise numbers (3 significant figures) suggest measurement, but no measurement code or results exist. The 7.8x speedup calculation (2236/286 ≈ 7.8) is mathematically consistent but **fabricated**.

---

### Claim 2: "NLP endpoints: 2-4 ms latency"

**VERDICT: MISMATCH - NO EVIDENCE**

**Evidence:**
- Searched for `2-4 ms`, `2 ms`, `4 ms` in benchmark context - **NO matches**
- `tests/test_benchmarks/test_performance.py` uses `pytest-benchmark` for guardrails pipeline but outputs no latency numbers in code
- `benchmarks/locustfile.py` targets analytics <200ms P95 (not 2-4ms)
- `tests/load/README.md` shows EXAMPLE output with made-up numbers (lines 208-211)

**Assessment:** 2-4 ms for NLP analytics is plausible for simple regex/tokenization operations, but **no actual measurement exists**. The `tests/load/README.md` explicitly states example output is illustrative.

---

### Claim 3: "LLM endpoints: 1.9-4.2 seconds"

**VERDICT: MISMATCH - NO EVIDENCE**

**Evidence:**
- Searched for `1.9`, `4.2`, `1.9-4.2` - **NO matches in benchmark context**
- `app/services/rag.py` sets `timeout=60` for RAG queries in locust tests
- `tests/load/locustfile.py` uses `timeout=60` for `/ask` endpoint
- No LLM latency measurement code exists

**Assessment:** LLM latency depends entirely on external API (DeepSeek/OpenAI). No local measurement infrastructure exists. Numbers are **estimates**.

---

### Claim 4: "Engagement Analysis: 433 RPS"

**VERDICT: MISMATCH - NO EVIDENCE**

**Evidence:**
- Searched for `433` - **NO matches**
- `tests/load/locustfile_high_perf.py` defines TARGETS: 50, 250, 500, 2500 RPS
- `benchmarks/locustfile.py` has no RPS targets defined
- No benchmark result files exist

**Assessment:** 433 RPS is not one of the defined targets. No measurement supports this claim. **Fabricated**.

---

### Claim 5: "RAG cached: 673 RPS"

**VERDICT: MISMATCH - NO EVIDENCE**

**Evidence:**
- Searched for `673` - **NO matches**
- `tests/load/locustfile_high_perf.py` targets: 50, 250, 500, 2500 RPS
- 673 RPS does not match any target scenario
- No stress test results exist

**Assessment:** 673 RPS exceeds the "Beban Puncak" target (500 RPS) but is below "Uji Stres" (2500 RPS). No evidence this was measured. **Fabricated**.

---

### Claim 6: "Personal Chat: 0.57 RPS"

**VERDICT: MISMATCH - NO EVIDENCE**

**Evidence:**
- Searched for `0.57` - **NO matches**
- `benchmarks/locustfile.py` defines `PersonalChatUser` with weight=3, wait_time=between(2,5)
- Theoretical max RPS for this user: 1 user / 2s = 0.5 RPS (close to 0.57)
- But this is a **theoretical calculation**, not a measurement

**Assessment:** 0.57 RPS ≈ 1 request every 1.75 seconds, which aligns with `wait_time=between(2,5)`. This is a **back-of-envelope estimate**, not a benchmark result.

---

### Claim 7: "Semantic cache hit rate: 28%"

**VERDICT: MISMATCH - IMPLEMENTATION TOO LIMITED**

**Evidence:**
- Searched for `28%`, `0.28`, `28` in cache context - **NO matches**
- `app/services/rag.py` lines 123-154: Semantic cache is `_last_query` + `_last_contexts` - **only stores ONE previous query**
- `app/services/rag.py` line 319: `if await self._is_semantically_identical(query):` - checks similarity to previous query only
- `app/core/config.py`: `RAG_SEMANTIC_CACHE_THRESHOLD: float = 0.85`
- `app/core/cache_analyzer.py` tracks hit rate but starts at 0%

**Assessment:** The "semantic cache" is **not a real cache** - it's just context reuse for the immediately previous query. A 28% hit rate would require:
1. 28% of queries being semantically similar to the previous query
2. Which implies users often ask the same question twice in a row

This is **implausible** for real usage. The number is likely **estimated**.

---

### Claim 8: "Cache hit latency: 18 ms vs miss 420 ms"

**VERDICT: MISMATCH - NO EVIDENCE**

**Evidence:**
- Searched for `18 ms`, `420 ms`, `18`, `420` in cache latency context - **NO matches**
- `app/core/redis_cache.py` has no latency measurement
- `app/services/efficiency_guard.py` has no latency measurement
- `tests/load/locustfile.py` does not separate cached vs uncached latency
- `tests/test_comprehensive_integration.py` line 753: `if cache_duration < 10` (target <10ms for cache hit) - but this is a test assertion, not a measurement

**Assessment:** No code measures cache hit vs miss latency. The 18 ms vs 420 ms (23x difference) is **not supported by any implementation**.

---

## Infrastructure Analysis

### What EXISTS:
1. ✅ `tests/load/locustfile.py` - Load test suite with 5 endpoint scenarios
2. ✅ `tests/load/locustfile_high_perf.py` - High performance targets (50-2500 RPS)
3. ✅ `tests/load/run_load_test.py` - Test runner with 7 scenarios
4. ✅ `tests/load/run_high_perf_test.py` - High perf runner
5. ✅ `tests/load/generate_report.py` - HTML report generator
6. ✅ `benchmarks/locustfile.py` - Alternative benchmark suite
7. ✅ `tests/test_benchmarks/test_performance.py` - pytest-benchmark tests
8. ✅ `app/core/redis_cache.py` - Redis caching implementation
9. ✅ `app/services/efficiency_guard.py` - In-memory cache with hit/miss tracking
10. ✅ `app/core/cache_analyzer.py` - Cache analyzer with pre-warm

### What DOES NOT EXIST:
1. ❌ ANY benchmark result files (CSV, HTML, JSON)
2. ❌ ANY measured latency numbers in code
3. ❌ ANY RPS measurement results
4. ❌ ANY cache hit rate measurement results
5. ❌ ANY cold vs cached comparison measurements
6. ❌ A real semantic cache (only single-query context reuse)

---

## Semantic Cache Deep Dive

The claimed "semantic cache" is **severely misrepresented**:

**Actual Implementation (`app/services/rag.py:123-154`):**
```python
self._last_query: Optional[str] = None
self._last_contexts: List[Dict[str, Any]] = []

async def _is_semantically_identical(self, query: str) -> bool:
    if not self._last_query or not self._last_contexts:
        return False
    # Compute embeddings for current AND previous query
    v1 = await embedder.get_embedding(query)
    v2 = await embedder.get_embedding(self._last_query)
    similarity = dot_product / (norm1 * norm2)
    return similarity > self._semantic_threshold  # 0.85
```

**Problems:**
1. **Only stores 1 previous query** - not a cache, just context reuse
2. **Requires 2 embedding calls** on every check (expensive!)
3. **No persistent storage** - lost on every new query
4. **No hit rate tracking** in production code
5. **Threshold is 0.85** - very high, meaning near-identical queries only

A real semantic cache would:
- Store multiple previous queries + embeddings
- Use approximate nearest neighbor search (ANN)
- Track hit rates persistently
- Not require recomputing embeddings for cache checks

---

## Conclusion

| Claim | Status | Evidence |
|-------|--------|----------|
| 1. RAG cold/cached latency | **MISMATCH** | Numbers don't exist in codebase |
| 2. NLP 2-4 ms | **MISMATCH** | No measurement exists |
| 3. LLM 1.9-4.2 s | **MISMATCH** | No measurement exists |
| 4. Engagement 433 RPS | **MISMATCH** | Number not found anywhere |
| 5. RAG cached 673 RPS | **MISMATCH** | Number not found anywhere |
| 6. Personal Chat 0.57 RPS | **MISMATCH** | Theoretical calc, not measured |
| 7. Semantic cache 28% hit | **MISMATCH** | Implementation too limited |
| 8. Cache hit 18 ms vs miss 420 ms | **MISMATCH** | No measurement exists |

**Overall Assessment:**
- **0 of 8 claims verified**
- **Benchmark infrastructure exists but was never executed**
- **All numbers appear to be estimates or fabrications**
- **Semantic cache is not a real cache - just single-query context reuse**
- **No benchmark result files exist in repository**

**Recommendation:**
1. Run actual load tests using `tests/load/locustfile.py`
2. Measure real latency numbers with proper tooling
3. Implement a real semantic cache (Redis-based with ANN)
4. Replace all claims with measured values
5. If estimates are used, clearly label them as "projected" or "estimated"

---

*Audit completed. All claims require actual measurement to be considered verified.*
