## Context

Logic Listener (`app/services/logic_listener.py`) sudah berjalan secara fungsional — mendeteksi off-topic, silence, dan participation inequity menggunakan embedding similarity, timestamp tracking, dan Gini coefficient. Namun tidak ada mekanisme untuk mengukur seberapa akurat deteksi ini. Untuk keperluan sidang TA, klaim "sistem mendeteksi kualitas diskusi" harus didukung angka precision/recall/F1 yang dihitung terhadap ground truth yang jelas.

Pendekatan: buat gold standard dataset secara manual (30 segmen diskusi berlabel), lalu jalankan Logic Listener terhadap dataset tersebut dan hitung metrik evaluasi. Logic Listener tidak dimodifikasi — hanya dievaluasi.

## Goals / Non-Goals

**Goals:**
- Buat gold standard dataset 30 segmen diskusi berlabel untuk 3 intervention type
- Implementasi evaluation harness yang menjalankan Logic Listener terhadap dataset
- Hasilkan tabel precision, recall, F1 per intervention type yang bisa dimasukkan ke Bab 4 TA
- Semua evaluation bisa dijalankan ulang via satu perintah pytest

**Non-Goals:**
- Tidak mengubah Logic Listener logic (bukan improvement, hanya evaluasi)
- Tidak membuat UI untuk evaluasi
- Tidak mengintegrasikan evaluasi ke CI/CD pipeline
- Tidak membuat dataset lebih dari 30 segmen (cukup untuk bukti ilmiah terbatas)

## Decisions

**D1: Format gold standard dataset → JSON**

Alternatif: CSV, YAML, Python dict hardcoded.
Pilihan: JSON di `data/evaluation/logic_listener_gold_standard.json`.
Alasan: mudah dibaca manusia, mudah di-load Python, bisa di-version control, dan bisa ditunjukkan ke penguji sebagai artefak penelitian.

**D2: 30 segmen, distribusi 10 per intervention type**

Alternatif: lebih banyak (50+) atau lebih sedikit (10-15).
Pilihan: 30 segmen — 10 off-topic cases, 10 silence cases, 10 participation inequity cases.
Alasan: cukup untuk menghitung metrik yang bermakna, realistis untuk dibuat manual dalam waktu singkat, dan proporsional dengan scope evaluasi terbatas yang diklaim di TA.

**D3: Evaluation harness sebagai pytest test file**

Alternatif: script standalone, Jupyter notebook.
Pilihan: `tests/test_unit/test_logic_listener_evaluation.py`.
Alasan: terintegrasi dengan test suite yang sudah ada, bisa dijalankan dengan perintah yang sama (`pytest`), dan hasilnya konsisten dengan laporan coverage.

**D4: Logic Listener tidak dimodifikasi**

Alasan: tujuan adalah evaluasi, bukan improvement. Mengubah Logic Listener sekaligus dengan evaluasi akan membuat hasil evaluasi tidak mencerminkan sistem yang diklaim di TA.

## Risks / Trade-offs

- **[Risk] Dataset kecil (30 sampel) → metrik tidak stabil** → Mitigation: framing di TA harus eksplisit bahwa ini adalah evaluasi terbatas pada skenario yang dikontrol, bukan evaluasi produksi skala besar.
- **[Risk] Label gold standard subjektif** → Mitigation: buat labeling guideline yang jelas di dalam dataset JSON (field `labeling_rationale` per item).
- **[Risk] Logic Listener menggunakan embedding similarity yang butuh model loaded** → Mitigation: mock embedding service di evaluation harness, atau gunakan fixture teks yang sudah diketahui hasilnya.

## Open Questions

- Apakah evaluasi off-topic perlu mock embedding service atau bisa pakai real FastEmbed? (Jika real, test akan lambat dan butuh model downloaded)
- Apakah hasil evaluasi perlu disimpan ke file output (JSON/CSV) atau cukup di stdout pytest?
