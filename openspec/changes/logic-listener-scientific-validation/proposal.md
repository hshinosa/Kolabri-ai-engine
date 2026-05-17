## Why

Logic Listener saat ini hanya bisa dibuktikan secara fungsional — sistem berjalan dan menghasilkan output. Namun tanpa gold standard dataset, precision, recall, dan F1-score, klaim deteksi kualitas diskusi tidak bisa dipertahankan secara ilmiah di sidang TA. Penguji akan menyerang tepat di titik ini.

## What Changes

- Buat gold standard dataset: 30 contoh segmen diskusi berlabel (off-topic / on-topic, silence trigger / no trigger, inequity / no inequity)
- Implementasi evaluation harness: jalankan Logic Listener terhadap dataset, hitung precision, recall, F1 per intervention type
- Tambah `tests/test_unit/test_logic_listener_evaluation.py` untuk evaluation pipeline
- Tambah `data/evaluation/logic_listener_gold_standard.json` sebagai dataset
- Dokumentasikan hasil evaluasi (tabel precision/recall/F1) untuk dimasukkan ke Bab 4 TA

## Capabilities

### New Capabilities

- `logic-listener-evaluation`: Evaluation harness untuk mengukur akurasi Logic Listener terhadap gold standard dataset — menghasilkan precision, recall, F1 per intervention type (off_topic, silence, participation_inequity)
- `gold-standard-dataset`: Dataset berlabel 30 segmen diskusi yang merepresentasikan skenario nyata pembelajaran kolaboratif, digunakan sebagai ground truth untuk evaluasi

### Modified Capabilities

<!-- Tidak ada perubahan requirement pada capability yang sudah ada -->

## Impact

- `app/services/logic_listener.py` — tidak diubah, hanya dievaluasi
- `tests/test_unit/test_logic_listener_evaluation.py` — file baru, evaluation pipeline
- `data/evaluation/logic_listener_gold_standard.json` — file baru, gold standard dataset
- Hasil evaluasi (tabel metrik) → masuk ke `bab4.tex` di naskah TA
