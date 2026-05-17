## logic-listener-evaluation

Evaluation harness untuk mengukur akurasi Logic Listener terhadap gold standard dataset.

### Requirements

#### REQ-LLE-01: Evaluation Pipeline

Sistem harus menyediakan evaluation pipeline yang dapat:
- Memuat gold standard dataset dari `data/evaluation/logic_listener_gold_standard.json`
- Menjalankan Logic Listener terhadap setiap item dataset
- Membandingkan output Logic Listener dengan label ground truth
- Menghitung precision, recall, F1-score per intervention type

#### REQ-LLE-02: Metrik per Intervention Type

Evaluasi harus menghasilkan metrik terpisah untuk setiap intervention type:
- `off_topic` — precision, recall, F1
- `silence` — precision, recall, F1
- `participation_inequity` — precision, recall, F1
- Overall macro-average precision, recall, F1

#### REQ-LLE-03: Output Format

Hasil evaluasi harus dicetak dalam format tabel yang bisa langsung dikutip ke naskah TA:

```
Intervention Type       | Precision | Recall | F1
------------------------|-----------|--------|----
off_topic               |   0.XX    |  0.XX  | 0.XX
silence                 |   0.XX    |  0.XX  | 0.XX
participation_inequity  |   0.XX    |  0.XX  | 0.XX
Macro Average           |   0.XX    |  0.XX  | 0.XX
```

#### REQ-LLE-04: Reproducibility

- Evaluation harus bisa dijalankan ulang dengan `pytest tests/test_unit/test_logic_listener_evaluation.py -v`
- Hasil harus deterministik (tidak bergantung pada state eksternal yang berubah)
- Embedding service untuk off-topic detection harus di-mock agar tidak butuh model download saat test

#### REQ-LLE-05: Integrasi dengan Test Suite

- File evaluasi berada di `tests/test_unit/test_logic_listener_evaluation.py`
- Ditandai dengan marker `@pytest.mark.evaluation` agar bisa dijalankan terpisah
- Tidak boleh menurunkan coverage keseluruhan
