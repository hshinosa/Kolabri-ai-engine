## Why

Tiga improvement kecil yang masing-masing berdiri sendiri namun semuanya memperkuat kualitas AI Engine dan bukti ilmiah untuk thesis: reranker sudah terintegrasi tapi belum aktif by default, evaluasi RAG belum pernah dijalankan secara formal meski tooling-nya sudah ada, dan beberapa threshold penting masih hardcoded di service layer padahal sudah ada mekanisme config.

## What Changes

- **Aktifkan reranker**: ubah default `reranking_enabled` menjadi `True` di config dan pastikan `CrossEncoderReranker.enabled` aktif — tidak ada perubahan arsitektur, hanya toggle
- **RAG evaluation**: jalankan `rag_benchmark_runner.py` terhadap dataset query real, hasilkan tabel MRR / precision@k yang bisa dimasukkan ke Bab 4 TA, simpan hasil ke `data/evaluation/rag_evaluation_results.md`
- **Threshold consolidation**: audit semua threshold yang masih hardcoded di service layer (bukan di `config.py`), pindahkan ke `config.py` dengan nama yang konsisten, update service yang menggunakannya

## Capabilities

### New Capabilities

- `rag-evaluation`: Evaluation pipeline untuk mengukur kualitas RAG pipeline menggunakan dataset query-answer pairs, menghasilkan MRR, precision@k, dan answer relevance score yang bisa dikutip ke Bab 4 TA
- `rag-evaluation-dataset`: Dataset query-answer pairs untuk evaluasi RAG — minimal 20 query dengan expected answer dan expected source document

### Modified Capabilities

- `reranker-activation`: Ubah default reranker dari disabled menjadi enabled — `RERANKER_ENABLED` di config.py dan `reranking_enabled` di query plan
- `threshold-config`: Konsolidasi semua threshold yang masih hardcoded di service layer ke `config.py` — mencakup Logic Listener thresholds, NLP analytics thresholds, dan intervention thresholds

## Impact

- `app/core/config.py` — tambah/update threshold settings dan reranker flag
- `app/services/reranker.py` — update default enabled state
- `app/services/rag.py` — pastikan `reranking_enabled` mengambil dari config
- `app/services/logic_listener.py` — ganti hardcoded values dengan `settings.*`
- `app/services/nlp_analytics.py` — ganti hardcoded values dengan `settings.*`
- `data/evaluation/rag_evaluation_dataset.json` — file baru, dataset evaluasi RAG
- `data/evaluation/rag_evaluation_results.md` — file baru, hasil evaluasi
- Tidak ada breaking change pada API contracts
