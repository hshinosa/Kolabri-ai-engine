## rag-evaluation

Evaluation pipeline untuk mengukur kualitas RAG pipeline secara formal.

### Requirements

#### REQ-RE-01: Metrik yang Dihasilkan

Evaluation harus menghasilkan:
- **MRR@5** (Mean Reciprocal Rank): seberapa tinggi dokumen relevan muncul di top-5 hasil retrieval
- **Precision@3**: berapa proporsi dari 3 dokumen teratas yang relevan
- **Answer Keyword Coverage**: persentase `expected_answer_keywords` yang muncul di jawaban LLM

#### REQ-RE-02: Output Format

```
RAG Evaluation Results
======================
Dataset: 20 queries

Retrieval Metrics:
  MRR@5:        0.XX
  Precision@3:  0.XX

Answer Quality:
  Keyword Coverage: XX.X%

Per Query Type:
  factual     → MRR: 0.XX, P@3: 0.XX
  conceptual  → MRR: 0.XX, P@3: 0.XX
  procedural  → MRR: 0.XX, P@3: 0.XX
```

#### REQ-RE-03: Script Evaluasi

Evaluation dijalankan via script `scripts/run_rag_evaluation.py` (bukan pytest, karena butuh LLM API aktif):
```bash
python scripts/run_rag_evaluation.py --save-results
```

Flag `--save-results` menyimpan output ke `data/evaluation/rag_evaluation_results.md`.

#### REQ-RE-04: Reproducibility

- Script harus bisa dijalankan ulang dan menghasilkan hasil yang konsisten
- Gunakan `rag_benchmark_runner.py` yang sudah ada sebagai foundation
- Hasil disimpan dengan timestamp agar bisa dibandingkan antar run

#### REQ-RE-05: Integrasi dengan Thesis

Hasil evaluasi harus dalam format yang bisa langsung dikutip ke Bab 4 TA sebagai tabel LaTeX.
