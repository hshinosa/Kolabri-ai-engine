# Load Testing Suite for Kolabri AI Engine

> Issue: **KOL-42** - Load testing performa response time AI

## 📋 Ringkasan

Suite load testing ini menggunakan [Locust](https://locust.io/) untuk mengukur performa AI Engine pada berbagai tingkat beban. Tujuannya adalah:

- ✅ Mengukur response time endpoint-endpoint kritis
- ✅ Menentukan throughput maksimum sistem
- ✅ Mengidentifikasi bottleneck dan titik kegagalan
- ✅ Memberikan rekomendasi optimasi berbasis data

## 🗂️ Struktur File

```
tests/load/
├── README.md                    # Dokumentasi ini
├── requirements-loadtest.txt    # Dependencies load testing
├── locustfile.py               # Main Locust test scenarios
├── run_load_test.py            # Script runner dengan skenario pre-configured
├── generate_report.py          # HTML report generator
└── results/                    # Output directory (auto-generated)
    ├── ai_engine_load_test_stats.csv
    ├── ai_engine_load_test_stats_history.csv
    ├── ai_engine_load_test_failures.csv
    └── report_YYYYMMDD_HHMMSS.html
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd ai-engine/tests/load
pip install -r requirements-loadtest.txt
```

Atau menggunakan script runner:

```bash
python run_load_test.py --install
```

### 2. Pastikan AI Engine Running

```bash
# Di terminal lain, pastikan AI Engine berjalan
cd Kolabri-ai-engine
python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

Pastikan `.env` berisi `CORE_API_SECRET` (sama dengan yang dipakai Core-API). Locust memuat Bearer token otomatis via `locust_auth.py`.

Semua skenario memanggil **`/api/*`** (bukan path lama tanpa prefix).

### 3. Jalankan Load Test

#### Option A: Menggunakan Script Runner (Recommended)

```bash
# Skenario 1: Smoke Test (verifikasi cepat)
python run_load_test.py --scenario smoke

# Skenario 2: Load Test (traffic normal)
python run_load_test.py --scenario load

# Skenario 3: Stress Test (batas maksimum)
python run_load_test.py --scenario stress

# Skenario 4: Spike Test (lonjakan traffic)
python run_load_test.py --scenario spike

# Skenario 5: Endurance Test (stabilits jangka panjang)
python run_load_test.py --scenario endurance
```

#### Option B: Menggunakan Locust Langsung

```bash
# Mode UI (buka http://localhost:8089)
locust -f locustfile.py --host=http://localhost:8001

# Mode Headless (CLI)
locust -f locustfile.py \
    --host=http://localhost:8001 \
    --users 100 \
    --spawn-rate 10 \
    --run-time 5m \
    --headless \
    --csv=results/ai_engine_load_test
```

## 📊 Skenario Uji

### Traffic Distribution

| Endpoint | Weight | Deskripsi |
|----------|--------|-----------|
| `/api/health` | 10% | Baseline performance check |
| `/api/ask` (RAG) | 50% | Query utama - endpoint kritis |
| `/api/analytics/engagement` | 20% | Analisis engagement teks |
| `/api/efficiency/*` | 10% | Cache & rate limit stats |
| `/api/groups/*` | 10% | Group operations |

### User Classes

1. **AIEngineUser** - Simulasi user normal dengan think time 1-5 detik
2. **SpikeTestUser** - Burst traffic dengan minimal think time (0.1-0.5s)
3. **SteadyStateUser** - Traffic stabil untuk endurance testing

## 🎯 SLA Targets

| Metric | Target | Keterangan |
|--------|--------|------------|
| Response Time (p95) | < 3000ms | 95% request harus di bawah 3 detik |
| Response Time (avg) | < 1000ms | Rata-rata response time |
| Error Rate | < 1% | Maksimum 1% request gagal |
| Throughput | > 10 RPS | Minimum 10 request per detik |
| Availability | > 99% | Uptime harus di atas 99% |

## 📈 Hasil dan Report

Setelah test selesai, report HTML otomatis di-generate:

```bash
# Report tersimpan di:
results/report_YYYYMMDD_HHMMSS.html

# Buka di browser
open results/report_*.html
```

Report mencakup:
- ✅ Summary metrics (total requests, failures, RPS)
- ✅ Performance per endpoint (avg, median, min, max)
- ✅ Slowest endpoints identification
- ✅ Throughput analysis
- ✅ Failure analysis
- ✅ SLA compliance check
- ✅ Recommendations

## 🔧 Custom Parameters

### Custom Load Test

```bash
python run_load_test.py \
    --users 150 \
    --duration 15m \
    --spawn-rate 25 \
    --host http://staging.kolabri.ai:8001
```

### Test Specific Endpoint Tags

```bash
# Hanya test RAG endpoints
locust -f locustfile.py --tags=rag --host=http://localhost:8001

# Hanya test health dan efficiency
locust -f locustfile.py --tags=health --tags=efficiency

# Exclude group operations
locust -f locustfile.py --exclude-tags=group
```

### Export Data

```bash
# CSV files otomatis di-generate
# Stats: results/ai_engine_load_test_stats.csv
# History: results/ai_engine_load_test_stats_history.csv
# Failures: results/ai_engine_load_test_failures.csv
```

## 🐛 Troubleshooting

### Issue: `locust: command not found`

```bash
pip install locust
# atau
python run_load_test.py --install
```

### Issue: Connection refused

Pastikan AI Engine berjalan:

```bash
curl http://localhost:8001/health
```

### Issue: High failure rate

- Periksa logs AI Engine: `docker logs kolabri-ai-engine`
- Pastikan ChromaDB dan MongoDB running
- Cek memory dan CPU usage

## 📊 Contoh Output

```
🚀 AI ENGINE LOAD TEST STARTED
======================================================================
Target Host: http://localhost:8001
Test Scenarios: Health, RAG Query, Analytics, Efficiency, Group Ops
======================================================================

Type     Name                     Req/s  Fails   Avg    Min    Max   
--------|-----------------------|------|------|------|------|------|
POST     /ask (RAG Query)        12.50   0%    850ms  420ms  3200ms
GET      /health                  8.30   0%     45ms   20ms   150ms
POST     /analytics/engagement    5.20   0%    120ms   80ms   300ms
GET      /efficiency/statistics   2.10   0%     65ms   40ms   180ms
```

## 🔗 Referensi

- [Locust Documentation](https://docs.locust.io/)
- [Locust API Reference](https://docs.locust.io/en/stable/api.html)
- [HTTP Load Testing Best Practices](https://grafana.com/blog/2023/05/15/load-testing/)

## 📝 Checklist Sebelum Run

- [ ] AI Engine running di target host
- [ ] Dependencies terinstall (`pip install -r requirements-loadtest.txt`)
- [ ] Disk space cukup untuk output CSV
- [ ] Network akses ke target host
- [ ] (Opsional) Inform tim tentang load test (untuk production)

## 🎓 Tips

1. **Start Small**: Mulai dengan smoke test sebelum stress test
2. **Monitor Resources**: Pantau CPU, memory, dan I/O selama test
3. **Incremental Load**: Naikkan beban secara bertahap
4. **Document Results**: Simpan report untuk perbandingan
5. **Regular Testing**: Jalankan load test secara berkala (CI/CD)

---

**Dokumentasi**: KOL-42 - Load Testing Performa Response Time AI  
**Author**: AI-Engine Team  
**Last Updated**: 2026-03-12
