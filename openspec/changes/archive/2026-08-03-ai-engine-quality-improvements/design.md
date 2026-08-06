## Context

Tiga improvement independen yang masing-masing bisa dikerjakan terpisah:

1. **Reranker**: `ENABLE_RERANKING = True` sudah ada di `config.py` dan `reranker.enabled = settings.ENABLE_RERANKING and CROSS_ENCODER_AVAILABLE`. Artinya reranker aktif jika package cross-encoder tersedia. Perlu verifikasi bahwa `CROSS_ENCODER_AVAILABLE` benar-benar `True` di environment, dan pastikan reranker benar-benar digunakan di query pipeline.

2. **RAG Evaluation**: `rag_benchmark_runner.py` dan `rag_quality.py` sudah ada tapi belum pernah dijalankan secara formal dengan dataset real. Tidak ada hasil evaluasi yang terdokumentasi untuk Bab 4 TA.

3. **Threshold Consolidation**: `config.py` sudah punya beberapa threshold (`SILENCE_THRESHOLD_MINUTES`, `INTERVENTION_COOLDOWN_MINUTES`, dll), tapi `logic_listener.py` masih punya class-level constants yang tidak mengambil dari `settings`:
   - `OFF_TOPIC_SIMILARITY_THRESHOLD = 0.6`
   - `OFF_TOPIC_CONSECUTIVE_THRESHOLD = 3`
   - `SILENCE_THRESHOLD_MINUTES = 10` (duplikat dengan config!)
   - `PARTICIPATION_INEQUITY_THRESHOLD = 0.6`

## Goals / Non-Goals

**Goals:**
- Verifikasi dan pastikan reranker aktif di environment, dokumentasikan pengaruhnya terhadap retrieval quality
- Jalankan RAG evaluation formal dengan dataset 20 query, hasilkan MRR dan precision@k untuk Bab 4
- Pindahkan 4 threshold Logic Listener dari class constants ke `config.py`, hapus duplikasi `SILENCE_THRESHOLD_MINUTES`

**Non-Goals:**
- Tidak mengganti cross-encoder model atau arsitektur reranker
- Tidak membuat RAG evaluation framework baru (gunakan yang sudah ada)
- Tidak mengubah threshold values — hanya memindahkan ke config, nilai tetap sama

## Decisions

**D1: Reranker verification via health endpoint**

Tambah field `reranker_enabled` ke response `/api/health` agar status reranker bisa diverifikasi tanpa membaca kode. Ini juga berguna untuk debugging di production.

**D2: RAG evaluation dataset format — JSON, 20 items**

Sama dengan gold standard Logic Listener: JSON di `data/evaluation/`, 20 query-answer pairs dari materi kuliah nyata. Cukup untuk menghitung MRR@5 dan precision@3 yang bermakna.

**D3: Threshold di config.py pakai prefix `LOGIC_LISTENER_`**

Untuk menghindari konflik nama dan memperjelas ownership:
- `LOGIC_LISTENER_OFF_TOPIC_SIMILARITY_THRESHOLD: float = 0.6`
- `LOGIC_LISTENER_OFF_TOPIC_CONSECUTIVE_THRESHOLD: int = 3`
- `LOGIC_LISTENER_PARTICIPATION_INEQUITY_THRESHOLD: float = 0.6`
- `SILENCE_THRESHOLD_MINUTES` sudah ada — hapus duplikat di class constant

**D4: LogicListener baca dari settings saat `__init__`, bukan class constant**

Agar threshold bisa di-override via environment variable tanpa restart class definition.

## Risks / Trade-offs

- **[Risk] Cross-encoder model butuh download saat pertama kali** → Mitigation: dokumentasikan di README bahwa model akan di-download otomatis oleh FastEmbed/sentence-transformers saat pertama run
- **[Risk] RAG evaluation butuh LLM API aktif** → Mitigation: tandai test dengan `@pytest.mark.requires_llm`, jalankan manual bukan di CI
- **[Risk] Mengubah threshold dari class constant ke settings bisa break test yang mock LogicListener** → Mitigation: audit test yang ada sebelum mengubah, update mock jika perlu

## Open Questions

- Apakah cross-encoder model untuk reranker sudah ter-download di environment saat ini?
- Apakah 20 query untuk RAG evaluation cukup representatif, atau perlu lebih?
