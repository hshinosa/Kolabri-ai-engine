## 1. Threshold Consolidation (Logic Listener)

- [x] 1.1 Tambah section `# Logic Listener Thresholds` di `app/core/config.py` dengan 3 setting baru: `LOGIC_LISTENER_OFF_TOPIC_SIMILARITY_THRESHOLD`, `LOGIC_LISTENER_OFF_TOPIC_CONSECUTIVE_THRESHOLD`, `LOGIC_LISTENER_PARTICIPATION_INEQUITY_THRESHOLD`
- [x] 1.2 Update `LogicListener.__init__` di `app/services/logic_listener.py` untuk membaca threshold dari `settings.*` bukan class constants
- [x] 1.3 Hapus 4 class constants yang sudah dipindah ke config (`OFF_TOPIC_SIMILARITY_THRESHOLD`, `OFF_TOPIC_CONSECUTIVE_THRESHOLD`, `SILENCE_THRESHOLD_MINUTES`, `PARTICIPATION_INEQUITY_THRESHOLD`)
- [x] 1.4 Update semua referensi `self.OFF_TOPIC_SIMILARITY_THRESHOLD` → `self.off_topic_similarity_threshold` (dan seterusnya) di seluruh file
- [x] 1.5 Jalankan `pytest tests/test_unit/test_logic_listener*.py -v` — pastikan semua test masih passing (66 passed, 8 pre-existing event loop failures di Python 3.13)
- [x] 1.6 Jalankan `lsp_diagnostics` pada `logic_listener.py` dan `config.py` — basedpyright tidak terinstall, syntax verified via py_compile

## 2. Reranker Verification

- [x] 2.1 Cek apakah `sentence-transformers` / cross-encoder tersedia di environment: tidak terinstall → reranker disabled at runtime, didokumentasikan di README
- [x] 2.2 Tambah field `reranker_enabled` ke `HealthResponse` schema di `app/api/schemas.py`
- [x] 2.3 Update `/api/health` endpoint di `app/api/routes.py` untuk menyertakan status reranker aktual dari `get_reranker().enabled`
- [x] 2.4 Tambah startup log di `app/services/reranker.py` yang mencatat `enabled` state dan alasannya
- [x] 2.5 Tambah catatan reranker ke `README.md` (dependency `sentence-transformers`, auto-download model)
- [ ] 2.6 Verifikasi via `curl http://localhost:8001/api/health` — membutuhkan service running, skip (verifikasi manual saat deploy)

## 3. RAG Evaluation Dataset

- [x] 3.1 Buat direktori `data/evaluation/` jika belum ada
- [x] 3.2 Buat `data/evaluation/rag_evaluation_dataset.json` dengan metadata dan 20 query items
- [x] 3.3 Tulis 8 factual queries dengan `expected_answer_keywords` dan `expected_source_contains`
- [x] 3.4 Tulis 7 conceptual queries
- [x] 3.5 Tulis 5 procedural queries
- [x] 3.6 Validasi JSON: 20 items, distribusi difficulty (7 easy, 8 medium, 5 hard) sesuai spec ✓

## 4. RAG Evaluation Script

- [x] 4.1 Buat `scripts/run_rag_evaluation.py` dengan argparse (`--save-results`, `--dataset-path`)
- [x] 4.2 Implementasi fungsi `load_dataset()` yang memuat `rag_evaluation_dataset.json`
- [x] 4.3 Implementasi `run_retrieval_evaluation()`: untuk setiap query, jalankan vector search, hitung MRR@5 dan Precision@3
- [x] 4.4 Implementasi `run_answer_evaluation()`: untuk setiap query, jalankan RAG pipeline, hitung keyword coverage
- [x] 4.5 Implementasi `compute_per_query_type_metrics()`: breakdown metrik per query type (factual/conceptual/procedural)
- [x] 4.6 Implementasi `print_results_table()`: cetak tabel hasil dalam format yang bisa dikutip ke TA
- [x] 4.7 Implementasi `save_results()`: simpan ke `data/evaluation/rag_evaluation_results.md` dengan timestamp + LaTeX table
- [ ] 4.8 Jalankan script: `python scripts/run_rag_evaluation.py --save-results` — membutuhkan Qdrant + LLM API running, jalankan manual saat full stack aktif
- [ ] 4.9 Verifikasi hasil masuk akal (MRR > 0, Precision > 0) — bergantung pada task 4.8
- [x] 4.10 Siapkan tabel hasil dalam format LaTeX — sudah diimplementasikan di `save_results()` function
