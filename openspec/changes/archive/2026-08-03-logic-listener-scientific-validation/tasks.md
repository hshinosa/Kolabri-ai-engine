## 1. Gold Standard Dataset

- [x] 1.1 Buat direktori `data/evaluation/` di root project
- [x] 1.2 Buat `data/evaluation/logic_listener_gold_standard.json` dengan struktur metadata dan array items kosong
- [x] 1.3 Tulis 10 item `off_topic` (5 positive: harus intervensi, 5 negative: tidak perlu) dengan `labeling_rationale` per item
- [x] 1.4 Tulis 10 item `silence` (5 positive, 5 negative) dengan variasi `last_message_seconds_ago` yang realistis
- [x] 1.5 Tulis 10 item `participation_inequity` (5 positive, 5 negative) dengan variasi distribusi pesan per user
- [x] 1.6 Validasi JSON: pastikan file valid, total 30 items, distribusi seimbang

## 2. Evaluation Harness

- [x] 2.1 Buat `tests/test_unit/test_logic_listener_evaluation.py` dengan skeleton class dan import
- [x] 2.2 Implementasi fungsi `load_gold_standard()` yang memuat dataset dari JSON
- [x] 2.3 Implementasi mock untuk embedding service (agar off-topic evaluation tidak butuh model download)
- [x] 2.4 Implementasi `evaluate_off_topic()`: jalankan Logic Listener terhadap 10 off-topic items, kumpulkan TP/FP/FN
- [x] 2.5 Implementasi `evaluate_silence()`: jalankan Logic Listener terhadap 10 silence items, kumpulkan TP/FP/FN
- [x] 2.6 Implementasi `evaluate_participation_inequity()`: jalankan Logic Listener terhadap 10 inequity items, kumpulkan TP/FP/FN
- [x] 2.7 Implementasi `compute_metrics(tp, fp, fn)`: hitung precision, recall, F1
- [x] 2.8 Implementasi `print_evaluation_table()`: cetak tabel hasil dalam format yang bisa dikutip ke TA

## 3. Pytest Integration

- [x] 3.1 Tambah marker `evaluation` ke `pyproject.toml` markers list
- [x] 3.2 Tandai semua test di file evaluasi dengan `@pytest.mark.evaluation`
- [x] 3.3 Pastikan test bisa dijalankan dengan `pytest tests/test_unit/test_logic_listener_evaluation.py -v`
- [x] 3.4 Pastikan test tidak menurunkan coverage keseluruhan (tambah `# pragma: no cover` jika perlu pada bagian print)

## 4. Verifikasi & Dokumentasi Hasil

- [x] 4.1 Jalankan evaluation harness, catat hasil precision/recall/F1 per intervention type
- [x] 4.2 Simpan hasil evaluasi ke `data/evaluation/results.md` sebagai artefak penelitian
- [x] 4.3 Verifikasi hasil masuk akal (tidak semua 0 atau semua 1 — itu tanda ada bug di harness)
- [x] 4.4 Siapkan tabel hasil dalam format LaTeX untuk dimasukkan ke `bab4.tex`
